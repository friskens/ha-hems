"""HEMS wire protocol. Pure Python; never writes to equipment."""

from dataclasses import dataclass
import math
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from .const import DEFAULT_INTERVAL


_OMIT = object()


class ProtocolError(ValueError):
    """Unusable response; messages must never contain server bodies or secrets."""


def number(value, field, minimum=None, maximum=None):
    """Reject booleans, strings, NaN and infinity at the protocol boundary."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"invalid_{field}")
    if not math.isfinite(value):
        raise ProtocolError(f"invalid_{field}")
    if minimum is not None and value < minimum:
        raise ProtocolError(f"invalid_{field}")
    if maximum is not None and value > maximum:
        raise ProtocolError(f"invalid_{field}")
    return float(value)


def endpoint(value, default_path="/battery"):
    """Validate an HTTPS endpoint and add the contract path to a base URL."""
    try:
        value = value.strip()
        url = urlsplit(value)
        valid = (
            url.scheme == "https"
            and url.hostname
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
            and url.port != 0
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ProtocolError("invalid_endpoint")
    if not isinstance(default_path, str) or not default_path.startswith("/"):
        raise ProtocolError("invalid_endpoint")
    if url.path in ("", "/"):
        return urlunsplit((url.scheme, url.netloc, default_path, "", ""))
    return value.rstrip("/")


@dataclass(frozen=True)
class Decision:
    action: str
    power_kw: float
    received_at: float
    interval: int = DEFAULT_INTERVAL
    # Normalized response entries; None means missing/null, not "turn off".
    loads: tuple[dict, ...] | None = None
    # Informational response fields retained for the contract-driven UI only.
    presentation: dict | None = None
    ev_chargers: tuple[dict, ...] | None = None

    @property
    def effective(self):
        # Only actions without a power target ignore watts for deduplication.
        watts = (
            round(self.power_kw * 1000, 3)
            if self.action in {"charge", "chargesolar", "export", "peakshaving", "selfconsumption"}
            else 0.0
        )
        return self.action, watts


def _invalid_policy(definition: Mapping, field: str):
    """Return the declared invalid-value policy, defaulting to rejection.

    The contract is authoritative for whether optional bad data is discarded or
    makes the response unusable.  There is deliberately no client-side list of
    "informational" response fields here.
    """
    return _OMIT if definition.get("on_invalid") == "omit_field" else ProtocolError(f"invalid_{field}")


def _field_value(value, definition: Mapping, field: str):
    """Validate one declarative response field without interpreting it.

    This is a small schema interpreter, not a coercion layer.  In particular,
    it does not turn strings into numbers or execute contract text.  A field
    marked ``never_parse`` is still type-checked, but is otherwise passed
    through unchanged (used by human display text such as ``reason``).
    """
    kind = definition.get("type")
    try:
        if kind == "number":
            checked = number(value, field, definition.get("min"), definition.get("max"))
        elif kind == "integer":
            if type(value) is not int:
                raise ProtocolError(f"invalid_{field}")
            minimum, maximum = definition.get("min"), definition.get("max")
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                raise ProtocolError(f"invalid_{field}")
            checked = value
        elif kind == "boolean":
            if type(value) is not bool:
                raise ProtocolError(f"invalid_{field}")
            checked = value
        elif kind == "string":
            if not isinstance(value, str) or (definition.get("non_empty") is True and not value.strip()):
                raise ProtocolError(f"invalid_{field}")
            checked = value
        elif kind == "enum":
            if value not in definition.get("values", ()):
                raise ProtocolError(f"invalid_{field}")
            checked = value
        else:
            # Unknown future field kinds cannot be safely interpreted.  The
            # output is omitted, rather than allowing arbitrary JSON through.
            return _OMIT
    except ProtocolError:
        policy = _invalid_policy(definition, field)
        if policy is _OMIT:
            return _OMIT
        raise policy
    return value if definition.get("never_parse") is True else checked


def _contract_attributes(data, contract):
    """Retain only contract-declared response attributes from HEMS."""
    decision = contract.output("decision") if contract else None
    definitions = decision.get("attributes") if isinstance(decision, Mapping) else None
    if not isinstance(definitions, Mapping):
        return {}
    result = {}
    for name, definition in definitions.items():
        if name not in data or not isinstance(definition, Mapping) or definition.get("local") is True:
            continue
        value = _field_value(data[name], definition, name)
        if value is not _OMIT:
            result[name] = value
    return result


def _parse_entries(value, definition: Mapping, field: str):
    """Parse a list output from its entry schema in the contract."""
    if value is None:
        return None
    if not isinstance(value, list):
        policy = _invalid_policy(definition, field)
        if policy is _OMIT:
            return None
        raise policy
    schema = definition.get("entry")
    if not isinstance(schema, Mapping):
        # A contract did not declare a safe entry grammar.  Never expose raw
        # future JSON as a pseudo-entity attribute.
        return None
    parsed: list[dict] = []
    unique_seen: dict[str, set] = {}

    def field_value(raw_value, item: Mapping, name: str):
        """Use an entry policy first, otherwise inherit the list policy."""
        try:
            return _field_value(raw_value, item, name)
        except ProtocolError:
            policy = _invalid_policy(item if "on_invalid" in item else definition, name)
            if policy is _OMIT:
                return _OMIT
            raise policy

    for raw in value:
        if not isinstance(raw, Mapping):
            policy = _invalid_policy(definition, field)
            if policy is _OMIT:
                continue
            raise policy
        entry: dict = {}
        # Validate kind first: action and kind-restricted fields refer to it.
        kind_definition = schema.get("kind")
        if isinstance(kind_definition, Mapping) and "kind" in raw:
            parsed_kind = field_value(raw["kind"], kind_definition, "kind")
            if parsed_kind is not _OMIT:
                entry["kind"] = parsed_kind
        entry_kind = entry.get("kind")
        for name, item in schema.items():
            if name == "kind" or not isinstance(name, str) or not isinstance(item, Mapping):
                continue
            if name not in raw:
                if item.get("required") is True:
                    policy = _invalid_policy(item, name)
                    if policy is not _OMIT:
                        raise policy
                continue
            required_kind = item.get("kind")
            if required_kind is not None and entry_kind != required_kind:
                # An absent/invalid kind is a display-level inconsistency in
                # this optional field. Do not discard the battery decision.
                if entry_kind is None:
                    continue
                policy = _invalid_policy(item, name)
                if policy is not _OMIT:
                    raise policy
                continue
            parsed_value = field_value(raw[name], item, name)
            if parsed_value is _OMIT:
                continue
            values_by_kind = item.get("values_by_kind")
            if isinstance(values_by_kind, Mapping) and entry_kind in values_by_kind:
                allowed = values_by_kind[entry_kind]
                if not isinstance(allowed, (list, tuple)) or parsed_value not in allowed:
                    policy = _invalid_policy(item, name)
                    if policy is not _OMIT:
                        raise policy
                    continue
            entry[name] = parsed_value
            if item.get("unique_in_list") is True:
                values = unique_seen.setdefault(name, set())
                if parsed_value in values:
                    policy = _invalid_policy(item, name)
                    if policy is not _OMIT:
                        raise policy
                    entry.pop(name, None)
                    continue
                values.add(parsed_value)
        parsed.append(entry)
    return tuple(parsed)


def parse_response(data, received_at, contract=None):
    # Actions are service-owned extensible data.  A future action remains
    # observable even when this client has no local presentation translation.
    # Runtime code must still treat it as non-actuating unless explicitly known.
    if not isinstance(data, dict) or not isinstance(data.get("action"), str) or not data["action"].strip():
        raise ProtocolError("invalid_action")
    action = data["action"]
    if contract:
        decision_definition = contract.output("decision") or {}
        allowed_actions = decision_definition.get("values", ())
        if action not in allowed_actions:
            policy = _invalid_policy(decision_definition, "action")
            if policy is not _OMIT:
                raise policy
            # A decision without an action cannot be presented safely.
            raise ProtocolError("invalid_action")
    presentation = _contract_attributes(data, contract)
    if contract:
        decision_definition = contract.output("decision") or {}
        power_definition = decision_definition.get("attributes", {}).get("power_kw", {})
        required_for = power_definition.get("required_for", ())
        if "power_kw" in presentation:
            power = presentation["power_kw"]
        elif action in required_for:
            raise ProtocolError("invalid_power_kw")
        else:
            # ``default_otherwise`` is an output-contract rule.  The fallback
            # only preserves compatibility with a pre-contract caller.
            default = power_definition.get("default_otherwise", 0)
            power = number(default, "power_kw", 0)
            presentation["power_kw"] = power
        interval = presentation.get("command_interval_seconds", DEFAULT_INTERVAL)
    else:
        # Compatibility path for direct callers from pre-contract releases.
        power = number(
            data.get(
                "power_kw",
                None if action in {"charge", "chargesolar", "export", "peakshaving", "selfconsumption"} else 0,
            ),
            "power_kw",
            0,
        )
        interval = data.get("command_interval_seconds", DEFAULT_INTERVAL)
        if type(interval) is not int or interval <= 0:
            raise ProtocolError("invalid_interval")
        if "power_unit" in data and data["power_unit"] not in ("w", "kw"):
            raise ProtocolError("invalid_power_unit")
        if "soc" in data:
            number(data["soc"], "soc", 0, 100)
        presentation.update(power_kw=power, command_interval_seconds=interval)
    if contract:
        loads_definition = contract.output("loads")
        charger_definition = contract.output("ev_chargers")
        parsed = _parse_entries(
            data.get(loads_definition.get("from", "loads"))
            if isinstance(loads_definition, Mapping)
            else None,
            loads_definition,
            "loads",
        ) if isinstance(loads_definition, Mapping) else None
        parsed_chargers = _parse_entries(
            data.get(charger_definition.get("from", "ev_chargers"))
            if isinstance(charger_definition, Mapping)
            else None,
            charger_definition,
            "ev_chargers",
        ) if isinstance(charger_definition, Mapping) else None
    else:
        # Compatibility for pre-contract callers.  The supported runtime path
        # always supplies a contract, so this deliberately narrow fallback is
        # not a second source of semantics for contracted responses.
        parsed = _parse_entries(data.get("loads"), {
            "on_invalid": "reject_response",
            "entry": {
                "id": {"type": "string", "non_empty": True, "required": True, "unique_in_list": True},
                "action": {"type": "string", "non_empty": True, "required": True},
                "kind": {"type": "enum", "values": ["ev", "deferrable"], "on_invalid": "omit_field"},
                "name": {"type": "string", "on_invalid": "omit_field"},
                "reason": {"type": "string", "never_parse": True, "on_invalid": "omit_field"},
                "uid": {"type": "string", "on_invalid": "omit_field"},
                "power_kw": {"type": "number", "min": 0, "on_invalid": "reject_response"},
                "power_w": {"type": "number", "min": 0, "on_invalid": "omit_field"},
                "current_a": {"type": "number", "min": 0, "on_invalid": "reject_response"},
                "target_pct": {"type": "number", "min": 0, "max": 100, "on_invalid": "reject_response"},
                "reports_power": {"type": "boolean", "on_invalid": "omit_field"},
                "enabled": {"type": "boolean", "on_invalid": "omit_field"},
            },
        }, "loads")
        parsed_chargers = _parse_entries(data.get("ev_chargers"), {
            "on_invalid": "reject_response",
            "entry": {
                "id": {"type": "string", "on_invalid": "omit_field"},
                "uid": {"type": "string", "on_invalid": "omit_field"},
                "name": {"type": "string", "on_invalid": "omit_field"},
                "phases": {"type": "integer", "min": 1, "max": 3, "on_invalid": "omit_field"},
            },
        }, "ev_chargers")
    # The contract-derived presentation mapping intentionally contains no
    # client-maintained list of optional response fields.  Derived attributes
    # are evaluated later by the restricted presentation expression engine.
    return Decision(action, power, received_at, interval, parsed, presentation, parsed_chargers)


def changed(current, previous):
    if current.keys() != previous.keys():
        return True
    for key, value in current.items():
        # Stale is a diagnostic marker.  A transition to stale must not turn
        # an otherwise stable sample into an unsafe numeric comparison.
        if key == "stale":
            continue
        if key == "phase_current_a":
            if any(abs(current_a - previous_a) >= 1 for current_a, previous_a in zip(value, previous[key])):
                return True
        elif abs(value - previous[key]) >= (1 if key in {"soc", "ev_soc_pct"} else 200):
            return True
    return False


def due(now, last_attempt, last_success, interval, sample, previous, cadence=None):
    """Return whether an exchange is due under declared cadence data.

    ``interval`` remains a compatibility argument for callers predating the
    contract.  A validated contract cadence takes precedence: the response's
    command interval is presentation data, not an undeclared scheduling rule.
    """
    every_s = cadence.every_s if cadence else interval
    min_spacing_s = cadence.min_spacing_s if cadence else 20
    quarter_enabled = cadence.also_at_quarter_hour if cadence else True
    quarter = quarter_enabled and int(now // 900) != int(last_attempt // 900)
    return (quarter or now - last_attempt >= min_spacing_s) and (
        quarter or now - last_success >= every_s or changed(sample, previous)
    )
