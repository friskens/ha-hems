"""Repairs boundary for invalid HEMS telemetry configuration.

Only broken selections and invalid contract-compatible inputs belong here.
Temporary stale readings are telemetry, not a Repair, and no issue in this
module causes a service call, script invocation, or automation change.
"""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


def issue_id(entry_id: str, input_key: str) -> str:
    """Use a stable per-entry issue id so an options-flow repair resolves it."""
    return f"{entry_id}_telemetry_{input_key}"


async def async_set_input_issues(
    hass,
    entry_id: str,
    invalid_inputs: Iterable[str],
    known_inputs: Iterable[str],
) -> None:
    """Synchronize configuration/validation issues for one config entry.

    ``known_inputs`` comes from the already validated contract.  Supplying it
    avoids discovering arbitrary issues in the registry and keeps cleanup
    confined to this integration entry.
    """
    active = {key for key in invalid_inputs if isinstance(key, str) and key}
    known = {key for key in known_inputs if isinstance(key, str) and key}
    for key in known - active:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry_id, key))
    for key in active:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id(entry_id, key),
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="telemetry_input_invalid",
            translation_placeholders={"input": key},
        )
