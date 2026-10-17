"""Contract-neutral presentation primitives for HEMS-owned HA entities.

This module deliberately does not read a JSON file or Home Assistant state.  The
contract consumer supplies already validated input definitions and decisions;
the HA layer turns those into a small, stable presentation model.  Keeping that
seam explicit prevents a downloaded contract from becoming executable code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


KNOWN_DOMAINS = frozenset({"sensor"})


@dataclass(frozen=True)
class TelemetryInput:
    """A safe input selector description supplied by a validated contract."""

    key: str
    field: str
    required: bool
    multiple: bool = False
    domain: str = "sensor"
    device_class: str | None = None
    units: tuple[str, ...] = ()
    group: str | None = None
    options: tuple[str, ...] = ()


def telemetry_inputs(contract_inputs: Mapping[str, Any]) -> tuple[TelemetryInput, ...]:
    """Expose known selector building blocks and ignore unusable future fields.

    The contract validator owns acceptance of the full contract.  This function
    is intentionally conservative at the UI boundary: malformed or unsupported
    definitions are omitted instead of constructing arbitrary HA selectors.
    """
    result: list[TelemetryInput] = []
    for key, raw in contract_inputs.items():
        if not isinstance(key, str) or not isinstance(raw, Mapping):
            continue
        field, domain = raw.get("field"), raw.get("domain", "sensor")
        if not isinstance(field, str) or domain not in KNOWN_DOMAINS:
            continue
        units_value = raw.get("units", (raw.get("unit"),))
        if not isinstance(units_value, (list, tuple)):
            continue
        units = tuple(unit for unit in units_value if isinstance(unit, str))
        if len(units) != len(units_value):
            continue
        options = raw.get("options", ())
        if not isinstance(options, (list, tuple)) or not all(isinstance(v, str) for v in options):
            continue
        device_class = raw.get("device_class")
        group = raw.get("group")
        if device_class is not None and not isinstance(device_class, str):
            continue
        if group is not None and not isinstance(group, str):
            continue
        result.append(
            TelemetryInput(
                key=key,
                field=field,
                required=raw.get("required") is True,
                multiple=raw.get("multiple") is True,
                domain=domain,
                device_class=device_class,
                units=units,
                group=group,
                options=tuple(options),
            )
        )
    return tuple(result)
