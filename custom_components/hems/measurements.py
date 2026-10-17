"""Normalize existing HA observations; no device polling or invented zeroes."""

from dataclasses import dataclass, field
import math
from typing import Mapping

from .const import PHASE_CURRENT_ENTITY_KEYS
from .contract import ContractError, load_bundled_contract
from .local_transformations import TransformationError, evaluate, expression_uses_values
from .telemetry_config import is_selectable, option_flag_key, selected_entities


@dataclass(frozen=True)
class Observation:
    value: object
    unit: str | None
    reported_at: float


def normalize(observation, now, kind, max_age=120, invert=False):
    if observation is None or (max_age is not None and not 0 <= now - observation.reported_at < max_age):
        return None
    try:
        value = float(observation.value)
    except (TypeError, ValueError):
        return None
    if isinstance(observation.value, bool) or not math.isfinite(value):
        return None
    if kind == "soc":
        return value if observation.unit == "%" and 0 <= value <= 100 else None
    if kind == "current":
        if observation.unit == "mA":
            value /= 1000
        elif observation.unit != "A":
            return None
        return value if abs(value) <= 250 else None
    if observation.unit not in ("W", "kW"):
        return None
    value *= 1000 if observation.unit == "kW" else 1
    return -value if invert else value


def collect_with_sources(options, observe, now, max_age=300):
    """Collect valid current observations and their source report times.

    This is deliberately still tied to the existing options keys.  A later
    contract-driven options flow can supply more inputs, but it must not turn
    arbitrary contract expressions into executable collection logic.
    """
    if any(key.startswith("telemetry_") for key in options):
        try:
            return collect_contract_with_sources(options, observe, now, load_bundled_contract())
        except ContractError:
            # Never send an unchecked shape when the packaged contract is
            # unavailable or invalid. Runtime surfaces this diagnostically.
            return {}, ["contract"], {}
    # Grid: +import. Battery: +charge. Solar: nonnegative DC production.
    sample, invalid, reported = {}, [], {}
    mapping = {
        "soc": "soc_entity",
        "grid_power": "grid_entity",
        "battery_power": "battery_entity",
        "ev_power_w": "ev_power_entity",
        "ev_soc_pct": "ev_soc_entity",
    }
    for measurement_field, config in mapping.items():
        entity = options.get(config)
        if not entity:
            if measurement_field in ("soc", "grid_power", "battery_power"):
                invalid.append(measurement_field)
            continue
        # EV SOC freshness belongs to its source integration. Legacy timeout and
        # timestamp options are intentionally ignored, including existing entries.
        age = None if measurement_field == "ev_soc_pct" else max_age
        obs = observe(entity)
        value = normalize(
            obs,
            now,
            "soc" if measurement_field in ("soc", "ev_soc_pct") else "power",
            age,
            options.get("invert_" + measurement_field, False),
        )
        if value is None or (measurement_field == "ev_power_w" and value < 0):
            invalid.append(measurement_field)
        else:
            sample[measurement_field] = value
            reported[measurement_field] = obs.reported_at
    solar_observations = [observe(entity) for entity in options.get("solar_entities", [])]
    solar = [normalize(observation, now, "power", max_age) for observation in solar_observations]
    if not solar or any(value is None or value < 0 for value in solar):
        invalid.append("solar_power")
    else:
        sample["solar_power"] = sum(solar)
        reported["solar_power"] = min(observation.reported_at for observation in solar_observations)
    phase_entities = [options.get(key) for key in PHASE_CURRENT_ENTITY_KEYS]
    if any(phase_entities):
        if not all(phase_entities):
            invalid.append("phase_current_a")
        else:
            phase_observations = [observe(entity) for entity in phase_entities]
            phase_currents = [normalize(observation, now, "current", max_age) for observation in phase_observations]
            if any(value is None for value in phase_currents):
                invalid.append("phase_current_a")
            else:
                sample["phase_current_a"] = [abs(value) for value in phase_currents]
                reported["phase_current_a"] = min(observation.reported_at for observation in phase_observations)
    return sample, invalid, reported


def collect(options, observe, now):
    """Return current values for compatibility with existing callers/tests."""
    sample, invalid, _reported = collect_with_sources(options, observe, now)
    return sample, invalid


@dataclass
class MeasurementCache:
    """Last valid telemetry values, without invented substitutes.

    Values are retained only after the source supplied a valid measurement.
    ``payload`` reports source fields which have crossed their contract stale
    limit, but intentionally keeps transmitting their last real value.
    """

    values: dict[str, object] = field(default_factory=dict)
    reported_at: dict[str, float] = field(default_factory=dict)

    def update(self, sample: Mapping[str, object], reported: Mapping[str, float]) -> None:
        for name, value in sample.items():
            timestamp = reported.get(name)
            if timestamp is None:
                continue
            # Do not replace a newer valid observation with an old state event.
            if timestamp >= self.reported_at.get(name, float("-inf")):
                self.values[name] = value
                self.reported_at[name] = timestamp

    def missing_required(self, fields: tuple[str, ...]) -> bool:
        return any(field not in self.values for field in fields)

    def payload(self, now: float, stale_after: Mapping[str, int | None]) -> dict[str, object]:
        payload = dict(self.values)
        stale = sorted(
            name
            for name, timestamp in self.reported_at.items()
            if (limit := stale_after.get(name)) is not None and now - timestamp >= limit
        )
        if stale:
            payload["stale"] = stale
        return payload
def collect_contract_with_sources(options, observe, now, contract):
    """Collect telemetry by applying the contract's bounded local rules.

    Rules are interpreted by a restricted arithmetic grammar, never Python or
    HA templates.  Units, signs, aggregations, groups and ranges originate in
    the contract rather than a client list of equipment-specific cases.
    """
    sample, invalid, reported = {}, set(), {}
    rules = contract.raw.get("rules", {})
    if not isinstance(rules, Mapping):
        return {}, ["contract"], {}
    groups = {}
    expected_groups = {}
    for input_spec in contract.inputs.values():
        if is_selectable(input_spec) and input_spec.group:
            expected_groups.setdefault(input_spec.group, []).append(input_spec)
    for input_spec in contract.inputs.values():
        if not is_selectable(input_spec):
            continue
        entities = selected_entities(input_spec, options)
        if not entities:
            if input_spec.required:
                invalid.add(input_spec.field)
            continue
        observations = [observe(entity) for entity in entities]
        values = [_contract_value(input_spec, observation, now, options, rules) for observation in observations]
        if any(value is None for value in values):
            aggregate_rule = _aggregate_rule(input_spec, rules) if input_spec.multiple else None
            if not aggregate_rule or aggregate_rule.get("all_sources_required", True) is not False:
                invalid.add(input_spec.field)
                continue
        valid = [
            (value, observation.reported_at)
            for value, observation in zip(values, observations, strict=True)
            if value is not None and observation is not None
        ]
        if not valid:
            invalid.add(input_spec.field)
            continue
        values, report_times = zip(*valid, strict=True)
        values, report_times = list(values), list(report_times)
        if input_spec.group:
            if len(values) != 1:
                invalid.add(input_spec.field)
            else:
                groups.setdefault(input_spec.group, []).append((input_spec, values[0], report_times[0]))
        elif input_spec.multiple:
            value = _aggregate_contract_values(input_spec, values, options, rules)
            if value is None:
                invalid.add(input_spec.field)
            else:
                sample[input_spec.field] = value
                reported[input_spec.field] = min(report_times)
        else:
            sample[input_spec.field] = values[0]
            reported[input_spec.field] = report_times[0]
    for group, members in groups.items():
        assembled = _assemble_contract_group(group, members, expected_groups[group], rules)
        if assembled is None:
            invalid.update(member.field for member, _value, _reported in members)
            continue
        field, values, timestamp = assembled
        sample[field] = values
        reported[field] = timestamp
    return sample, sorted(invalid), reported


def _input_rules(rules, input_key):
    """Rules are applicable only when the contract explicitly says so."""
    return [
        rule for rule in rules.values()
        if isinstance(rule, Mapping)
        and isinstance(rule.get("applies_to"), (list, tuple))
        and input_key in rule["applies_to"]
        and isinstance(rule.get("expression"), str)
    ]


def _contract_value(input_spec, observation, now, options, rules):
    if observation is None:
        return None
    if input_spec.stale_after_s is not None and not 0 <= now - observation.reported_at < input_spec.stale_after_s:
        return None
    if observation.unit not in input_spec.units:
        return None
    try:
        value = float(observation.value)
    except (TypeError, ValueError):
        return None
    if isinstance(observation.value, bool) or not math.isfinite(value):
        return None
    declared_options = {
        name: bool(options.get(option_flag_key(input_spec.key, name), False))
        for name in input_spec.options
    }
    try:
        for rule in _input_rules(rules, input_spec.key):
            if expression_uses_values(rule["expression"]):
                continue
            value = evaluate(rule["expression"], value=value, unit=observation.unit, options=declared_options)
            digits = rule.get("round")
            if type(digits) is int and digits >= 0:
                value = round(value, digits)
    except TransformationError:
        return None
    return value


def _aggregate_contract_values(input_spec, values, options, rules):
    declared_options = {
        name: bool(options.get(option_flag_key(input_spec.key, name), False))
        for name in input_spec.options
    }
    rule = _aggregate_rule(input_spec, rules)
    if rule is None:
        return None
    try:
        value = evaluate(rule["expression"], values=values, options=declared_options)
        digits = rule.get("round")
        return round(value, digits) if type(digits) is int and digits >= 0 else value
    except TransformationError:
        return None


def _aggregate_rule(input_spec, rules):
    aggregate_rules = [
        rule for rule in _input_rules(rules, input_spec.key) if expression_uses_values(rule["expression"])
    ]
    return aggregate_rules[0] if len(aggregate_rules) == 1 else None


def _assemble_contract_group(group, members, expected_members, rules):
    group_rules = [rule for rule in rules.values() if isinstance(rule, Mapping) and rule.get("group") == group]
    if len(group_rules) != 1:
        return None
    if group_rules[0].get("all_or_none") is not True or len(members) != len(expected_members):
        return None
    fields = {member.field for member, _value, _reported in members}
    ordered = sorted(members, key=lambda member: member[0].definition.get("index", -1))
    indexes = [member.definition.get("index") for member, _value, _reported in ordered]
    if len(fields) != 1 or indexes != list(range(len(ordered))):
        return None
    values = [value for _member, value, _reported in ordered]
    range_definition = group_rules[0].get("range")
    if isinstance(range_definition, (list, tuple)) and len(range_definition) == 2:
        lower, upper = range_definition
        if not all(isinstance(bound, (int, float)) and not isinstance(bound, bool) for bound in (lower, upper)):
            return None
        if any(value < lower or value > upper for value in values):
            return None
    elif range_definition is not None:
        return None
    return next(iter(fields)), values, min(timestamp for _member, _value, timestamp in ordered)


def collect_contract(options, observe, now, contract):
    """Compatibility wrapper for contract-driven callers and focused tests."""
    sample, invalid, _reported = collect_contract_with_sources(options, observe, now, contract)
    return sample, invalid
