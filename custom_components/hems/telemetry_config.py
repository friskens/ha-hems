"""Declarative telemetry selection helpers.

The contract owns input keys and meaning.  This module only maps those keys to
options-flow storage and validates a user's selection of existing HA entities.
It never evaluates contract expressions, creates a helper, or changes an
automation or a device.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .contract import ContractInput, HemsContract


OPTION_PREFIX = "telemetry_"

# These aliases retain existing a9 selections during the move to contract input
# keys.  They are intentionally one-way: newly saved options use only the
# contract-derived names.
LEGACY_ENTITY_KEYS = {
    "battery_soc": "soc_entity",
    "grid_power": "grid_entity",
    "battery_power": "battery_entity",
    "solar_sources": "solar_entities",
    "ev_power": "ev_power_entity",
    "ev_soc": "ev_soc_entity",
    "grid_meter_current_l1": "phase_l1_current_entity",
    "grid_meter_current_l2": "phase_l2_current_entity",
    "grid_meter_current_l3": "phase_l3_current_entity",
}


def option_key(input_key: str) -> str:
    """Return the stable persisted key for one contract input."""
    return f"{OPTION_PREFIX}{input_key}"


def option_flag_key(input_key: str, option: str) -> str:
    """Return a stable persisted key for a declared input option."""
    return f"{option_key(input_key)}_{option}"


def is_selectable(input_spec: ContractInput) -> bool:
    """Whether this input is one user-selected HA source.

    Per-output-entry fields describe data tied to a HEMS-owned load entry, not
    a single household sensor.  Asking the user for one global entity there
    would silently change the contract's meaning.
    """
    return input_spec.definition.get("per_output_entry") is not True


def defaults_for_contract(contract: HemsContract, existing: Mapping[str, Any]) -> dict[str, Any]:
    """Map current or a9 options to contract-derived option keys.

    Unknown options are ignored.  They may be owned by another version of the
    integration, and copying them would make a downloaded contract executable
    by accident.
    """
    defaults: dict[str, Any] = {}
    for input_spec in contract.inputs.values():
        if not is_selectable(input_spec):
            continue
        key = option_key(input_spec.key)
        value = existing.get(key, existing.get(LEGACY_ENTITY_KEYS.get(input_spec.key, "")))
        if input_spec.multiple:
            defaults[key] = list(value) if isinstance(value, (list, tuple)) else []
        elif isinstance(value, str) and value:
            defaults[key] = value
        for option in input_spec.options:
            flag = option_flag_key(input_spec.key, option)
            legacy = f"invert_{input_spec.field}"
            defaults[flag] = bool(existing.get(flag, existing.get(legacy, False)))
    return defaults


def selected_entities(input_spec: ContractInput, options: Mapping[str, Any]) -> tuple[str, ...]:
    """Return well-formed persisted entity IDs, without looking them up."""
    selected = options.get(option_key(input_spec.key))
    values = selected if input_spec.multiple else (selected,)
    if not isinstance(values, (tuple, list)):
        return ()
    return tuple(value for value in values if isinstance(value, str) and value)


def selection_errors(contract: HemsContract, options: Mapping[str, Any]) -> dict[str, str]:
    """Validate required/multiple/group shape before an entry is saved."""
    errors: dict[str, str] = {}
    groups: dict[str, list[ContractInput]] = {}
    for input_spec in contract.inputs.values():
        if not is_selectable(input_spec):
            continue
        selected = selected_entities(input_spec, options)
        if input_spec.required and not selected:
            errors[input_spec.key] = "required"
        if input_spec.group:
            groups.setdefault(input_spec.group, []).append(input_spec)
    for members in groups.values():
        configured = [bool(selected_entities(member, options)) for member in members]
        if any(configured) and not all(configured):
            for member in members:
                errors[member.key] = "incomplete_group"
    return errors


@dataclass(frozen=True)
class SelectedState:
    """The limited state metadata needed to validate a saved selection."""

    entity_id: str
    domain: str
    device_class: str | None
    unit: str | None


def invalid_configured_inputs(
    contract: HemsContract,
    options: Mapping[str, Any],
    lookup: Callable[[str], SelectedState | None],
) -> set[str]:
    """Find broken saved selections, never transient stale readings.

    A source reporting late is still structurally valid and must not create a
    Repair.  Freshness is handled by telemetry exchange, not this function.
    """
    invalid = set(selection_errors(contract, options))
    for input_spec in contract.inputs.values():
        if not is_selectable(input_spec):
            continue
        for entity_id in selected_entities(input_spec, options):
            state = lookup(entity_id)
            if state is None or state.domain != input_spec.domain:
                invalid.add(input_spec.key)
                break
            if input_spec.device_class and state.device_class != input_spec.device_class:
                invalid.add(input_spec.key)
                break
            if input_spec.units and state.unit not in input_spec.units:
                invalid.add(input_spec.key)
                break
    return invalid


def known_input_keys(contract: HemsContract) -> Iterable[str]:
    """Return only contract-validated keys for Repair cleanup."""
    return contract.inputs.keys()
