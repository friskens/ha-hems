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


@dataclass(frozen=True)
class FollowedStatus:
    """Informational assessment only; it never asks HA to actuate anything."""

    state: str
    reason: str
    action: str | None
    since: float | None


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


def connection_state(last_success: float | None, now: float) -> str:
    """Return the contract's presentation-only connection state."""
    if last_success is None or last_success <= 0:
        return "disconnected"
    age = max(0, now - last_success)
    if age < 150:
        return "connected"
    if age < 600:
        return "warning"
    return "disconnected"


def decision_is_fresh(received_at: float | None, now: float, max_age: float = 90) -> bool:
    """A future timestamp is not fresh; clocks must not make a decision valid."""
    return received_at is not None and 0 <= now - received_at < max_age


def followed_status(
    *,
    action: str | None,
    received_at: float | None,
    observation: bool | None,
    observed_at: float | None,
    now: float,
    grace_seconds: float = 180,
) -> FollowedStatus:
    """Produce an honest soft status from a separate, local observation.

    ``observation`` is deliberately a boolean/None supplied by a future
    contract-defined evaluator.  This client does not infer a vendor state,
    run a template, or command equipment.  ``None`` means there is insufficient
    evidence and must remain distinguishable from ``False``.
    """
    if action is None or received_at is None:
        return FollowedStatus("cannot_tell", "no_decision", action, received_at)
    if not decision_is_fresh(received_at, now):
        return FollowedStatus("cannot_tell", "decision_stale", action, received_at)
    if now - received_at < grace_seconds:
        return FollowedStatus("waiting", "grace_period", action, received_at)
    if observation is None or observed_at is None or observed_at < received_at:
        return FollowedStatus("cannot_tell", "no_current_observation", action, received_at)
    return FollowedStatus(
        "following" if observation else "not_following",
        "observation_matches" if observation else "observation_differs",
        action,
        received_at,
    )
