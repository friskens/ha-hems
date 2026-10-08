"""Intentionally small diagnostics: no keys, URL, entity IDs or raw responses."""

from .const import VERSION


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    return {
        "version": VERSION,
        "execution": runtime.status,
        "error": runtime.error,
        "requested": runtime.recovery.requested,
        "failed_effective_command": runtime.recovery.failed,
        "invalid_fields": runtime.invalid,
        "decision_action": runtime.decision.action if runtime.decision else None,
        "last_success": runtime.last_success,
        "configured_fields": sorted(key for key in runtime.options if key.endswith("_entity")),
    }
