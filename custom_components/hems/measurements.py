"""Normalize existing HA observations; no device polling or invented zeroes."""

from dataclasses import dataclass, field
import math
from typing import Mapping

from .const import PHASE_CURRENT_ENTITY_KEYS
from .contract import ContractError, load_bundled_contract
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
    """Collect the supported declarative input surface from validated metadata.

    This recognizes only the fixed unit conversions and aggregation already
    defined by the HEMS exchange.  It deliberately does not run ``rules`` or
    ``expression`` text carried by the contract.
    """
    sample, invalid, reported = {}, [], {}
    groups = {}
    for input_spec in contract.inputs.values():
        if not is_selectable(input_spec):
            continue
        entities = selected_entities(input_spec, options)
        if not entities:
            if input_spec.required:
                invalid.append(input_spec.field)
            continue
        kind = (
            "soc"
            if input_spec.device_class == "battery"
            else "current"
            if input_spec.device_class == "current"
            else "power"
        )
        invert = "invert" in input_spec.options and bool(
            options.get(option_flag_key(input_spec.key, "invert"), False)
        )
        observations = [observe(entity) for entity in entities]
        values = [
            normalize(observation, now, kind, input_spec.stale_after_s, invert)
            for observation in observations
        ]
        if any(value is None for value in values):
            invalid.append(input_spec.field)
            continue
        if input_spec.field == "solar_power" and any(value < 0 for value in values):
            invalid.append(input_spec.field)
            continue
        if input_spec.group:
            groups.setdefault(input_spec.group, []).append((input_spec, values[0]))
        elif input_spec.multiple:
            # The current contract's only selectable aggregate is PV power.
            # Future aggregation kinds need an explicit declarative building
            # block before this client can consume them.
            if input_spec.field == "solar_power":
                sample[input_spec.field] = sum(values)
                reported[input_spec.field] = min(
                    observation.reported_at for observation in observations if observation is not None
                )
            else:
                invalid.append(input_spec.field)
        else:
            sample[input_spec.field] = values[0]
            reported[input_spec.field] = observations[0].reported_at
    for group, members in groups.items():
        if group != "phase_current" or len(members) != 3:
            invalid.append("phase_current_a")
            continue
        ordered = sorted(members, key=lambda member: member[0].definition.get("index", -1))
        values = [abs(value) for _, value in ordered]
        if any(value > 250 for value in values):
            invalid.append("phase_current_a")
        else:
            sample["phase_current_a"] = values
            reported["phase_current_a"] = min(
                observe(entity).reported_at for input_spec, _value in ordered
                for entity in selected_entities(input_spec, options)
            )
    return sample, invalid, reported


def collect_contract(options, observe, now, contract):
    """Compatibility wrapper for contract-driven callers and focused tests."""
    sample, invalid, _reported = collect_contract_with_sources(options, observe, now, contract)
    return sample, invalid
