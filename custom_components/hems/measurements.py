"""Normalize existing HA observations; no device polling or invented zeroes."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Observation:
    value: object
    unit: str | None
    reported_at: float


def normalize(observation, now, kind, max_age=120, invert=False):
    if observation is None or not 0 <= now - observation.reported_at < max_age:
        return None
    try:
        value = float(observation.value)
    except (TypeError, ValueError):
        return None
    if isinstance(observation.value, bool) or not math.isfinite(value):
        return None
    if kind == "soc":
        return value if observation.unit == "%" and 0 <= value <= 100 else None
    if observation.unit not in ("W", "kW"):
        return None
    value *= 1000 if observation.unit == "kW" else 1
    return -value if invert else value


def collect(options, observe, now):
    """Grid: +import. Battery: +charge. Solar: nonnegative DC production."""
    sample, invalid = {}, []
    mapping = {
        "soc": "soc_entity",
        "grid_power": "grid_entity",
        "battery_power": "battery_entity",
        "ev_power_w": "ev_power_entity",
        "ev_soc_pct": "ev_soc_entity",
    }
    for field, config in mapping.items():
        entity = options.get(config)
        if not entity:
            if field in ("soc", "grid_power", "battery_power"):
                invalid.append(field)
            continue
        age = options.get("ev_soc_max_age", 900) if field == "ev_soc_pct" else 120
        obs = observe(entity)
        # Optional source timestamp protects against repeated cached cloud data.
        if field == "ev_soc_pct" and options.get("ev_soc_timestamp_entity"):
            source = observe(options["ev_soc_timestamp_entity"])
            try:
                from datetime import datetime

                stamp = datetime.fromisoformat(str(source.value)).timestamp()
                obs = Observation(obs.value, obs.unit, stamp)
            except (AttributeError, ValueError, TypeError):
                obs = None
        value = normalize(
            obs,
            now,
            "soc" if field in ("soc", "ev_soc_pct") else "power",
            age,
            options.get("invert_" + field, False),
        )
        if value is None or (field == "ev_power_w" and value < 0):
            invalid.append(field)
        else:
            sample[field] = value
    solar = [normalize(observe(entity), now, "power") for entity in options.get("solar_entities", [])]
    if not solar or any(value is None or value < 0 for value in solar):
        invalid.append("solar_power")
    else:
        sample["solar_power"] = sum(solar)
    return sample, invalid
