"""HEMS wire protocol. Pure Python; never writes to equipment."""

from dataclasses import dataclass
import math
from urllib.parse import urlsplit, urlunsplit

from .const import COMMANDS, DEFAULT_INTERVAL


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

    @property
    def effective(self):
        # Only actions without a power target ignore watts for deduplication.
        watts = (
            round(self.power_kw * 1000, 3)
            if self.action in {"charge", "chargesolar", "export", "peakshaving", "selfconsumption"}
            else 0.0
        )
        return self.action, watts


def parse_response(data, received_at):
    if not isinstance(data, dict) or data.get("action") not in COMMANDS:
        raise ProtocolError("invalid_action")
    action = data["action"]
    power = number(
        data.get(
            "power_kw",
            None if action in {"charge", "chargesolar", "export", "peakshaving", "selfconsumption"} else 0,
        ),
        "power_kw",
        0,
    )
    if "power" in data:
        number(data["power"], "power")  # Signed presentation, NOT a control value.
    if "power_unit" in data and data["power_unit"] not in ("w", "kw"):
        raise ProtocolError("invalid_power_unit")
    if "soc" in data:
        number(data["soc"], "soc", 0, 100)  # Informational; never a SOC target.
    interval = data.get("command_interval_seconds", DEFAULT_INTERVAL)
    if type(interval) is not int or interval <= 0:
        raise ProtocolError("invalid_interval")
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
                if field in load:
                    if not isinstance(load[field], str):
                        raise ProtocolError(f"invalid_{field}")
                    entry[field] = load[field]
            for field, maximum in (("current_a", None), ("target_pct", 100), ("power_kw", None)):
                if field in load:
                    entry[field] = number(load[field], field, 0, maximum)
            if "power_w" in load:
                entry["power_w"] = number(load["power_w"], "power_w", 0)
            if "reports_power" in load:
                if type(load["reports_power"]) is not bool:
                    raise ProtocolError("invalid_reports_power")
                entry["reports_power"] = load["reports_power"]
            parsed.append(entry)
        parsed = tuple(parsed)
    return Decision(action, power, received_at, interval, parsed)


def changed(current, previous):
    if current.keys() != previous.keys():
        return True
    return any(
        abs(value - previous[key]) >= (1 if key in {"soc", "ev_soc_pct"} else 200)
        for key, value in current.items()
    )


def due(now, last_attempt, last_success, interval, sample, previous):
    quarter = int(now // 900) != int(last_attempt // 900)
    return (quarter or now - last_attempt >= 20) and (
        quarter or now - last_success >= interval or changed(sample, previous)
    )
