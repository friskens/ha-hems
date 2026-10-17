"""HEMS wire protocol. Pure Python; never writes to equipment."""

from dataclasses import dataclass
import math
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from .const import DEFAULT_INTERVAL


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


def endpoint(value):
    """Validate an HTTPS endpoint and default a provider base URL to /battery."""
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
    if url.path in ("", "/"):
        return urlunsplit((url.scheme, url.netloc, "/battery", "", ""))
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


def _contract_attributes(data, contract):
    """Retain only declared, typed decision response fields from HEMS."""
    decision = contract.output("decision") if contract else None
    definitions = decision.get("attributes") if isinstance(decision, Mapping) else None
    if not isinstance(definitions, Mapping):
        return {}
    result = {}
    for name, definition in definitions.items():
        if name not in data or not isinstance(definition, Mapping) or definition.get("local") is True:
            continue
        value, kind = data[name], definition.get("type")
        try:
            if kind == "number":
                value = number(value, name, definition.get("min"), definition.get("max"))
            elif kind == "integer":
                if type(value) is not int or value < definition.get("min", value) or value > definition.get("max", value):
                    raise ProtocolError(f"invalid_{name}")
            elif kind == "enum":
                if value not in definition.get("values", ()):
                    raise ProtocolError(f"invalid_{name}")
            elif kind == "string":
                if not isinstance(value, str):
                    raise ProtocolError(f"invalid_{name}")
            else:
                continue
        except ProtocolError:
            if definition.get("on_invalid") == "omit_field":
                continue
            raise
        result[name] = value
    return result


def parse_response(data, received_at, contract=None):
    # Actions are service-owned extensible data.  A future action remains
    # observable even when this client has no local presentation translation.
    # Runtime code must still treat it as non-actuating unless explicitly known.
    if not isinstance(data, dict) or not isinstance(data.get("action"), str) or not data["action"].strip():
        raise ProtocolError("invalid_action")
    action = data["action"]
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
    loads = data.get("loads")
    parsed = None
    if loads is not None:
        if not isinstance(loads, list):
            raise ProtocolError("invalid_loads")
        parsed, seen = [], set()
        for load in loads:
            if not isinstance(load, dict):
                raise ProtocolError("invalid_load")
            load_id, load_action = load.get("id"), load.get("action")
            if (
                not isinstance(load_id, str)
                or not load_id.strip()
                or load_id in seen
                or not isinstance(load_action, str)
                or not load_action.strip()
            ):
                raise ProtocolError("invalid_load")
            seen.add(load_id)
            entry = {"id": load_id, "action": load_action}
            for field in ("kind", "name", "reason", "uid"):
                if isinstance(load.get(field), str):
                    entry[field] = load[field]
            for field, maximum in (("current_a", None), ("target_pct", 100), ("power_kw", None)):
                if field in load:
                    number(load[field], field, 0, maximum)
                    entry[field] = load[field]
            if "power_w" in load:
                try:
                    number(load["power_w"], "power_w", 0)
                except ProtocolError:
                    pass
                else:
                    entry["power_w"] = load["power_w"]
            if type(load.get("reports_power")) is bool:
                entry["reports_power"] = load["reports_power"]
            if type(load.get("enabled")) is bool:
                entry["enabled"] = load["enabled"]
            parsed.append(entry)
        parsed = tuple(parsed)
    chargers = data.get("ev_chargers")
    parsed_chargers = None
    if chargers is not None:
        if not isinstance(chargers, list):
            raise ProtocolError("invalid_ev_chargers")
        parsed_chargers = []
        for charger in chargers:
            if not isinstance(charger, dict):
                raise ProtocolError("invalid_ev_charger")
            entry = {}
            for field in ("id", "uid", "name"):
                if isinstance(charger.get(field), str) and charger[field].strip():
                    entry[field] = charger[field]
            if "phases" in charger:
                phases = charger["phases"]
                if type(phases) is int and 1 <= phases <= 3:
                    entry["phases"] = phases
            parsed_chargers.append(entry)
        parsed_chargers = tuple(parsed_chargers)
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


def due(now, last_attempt, last_success, interval, sample, previous):
    quarter = int(now // 900) != int(last_attempt // 900)
    return (quarter or now - last_attempt >= 20) and (
        quarter or now - last_success >= interval or changed(sample, previous)
    )
