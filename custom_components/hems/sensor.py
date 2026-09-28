"""Decision and execution status. Measured power is not inferred from commands."""

import time
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .entity import HemsEntity
from .const import COMMANDS

EXECUTION_STATES = [
    "starting",
    "observing",
    "stopped",
    "recovering",
    "observation_error",
    "restoring_auto",
    "applying",
    "settings_verified",
]


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    async_add_entities(
        [HemsSensor(runtime, key) for key in ("decision", "execution", "connection", "ev_soc")]
    )


class HemsSensor(HemsEntity, SensorEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key)
        self.key = key
        if key == "ev_soc":
            self._attr_native_unit_of_measurement = "%"
            self._attr_device_class = SensorDeviceClass.BATTERY
        else:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = {
                "decision": list(COMMANDS),
                "execution": EXECUTION_STATES,
                "connection": ["connected", "warning", "disconnected"],
            }[key]

    @property
    def native_value(self):
        r = self.runtime
        if self.key == "decision":
            return r.decision.action if r.decision else None
        if self.key == "execution":
            return r.status
        if self.key == "ev_soc":
            return r.previous.get("ev_soc_pct") if time.time() - r.last_success < 150 else None
        age = time.time() - r.last_success
        return "disconnected" if age >= 600 else "warning" if age >= 150 else "connected"

    @property
    def extra_state_attributes(self):
        r = self.runtime
        if self.key == "decision" and r.decision:
            return {
                "power_kw": r.decision.power_kw,
                "received_at": r.decision.received_at,
                "fresh": 0 <= time.time() - r.decision.received_at < 90,
                "loads": dict(r.decision.loads) if r.decision.loads is not None else None,
                "command_supported": r.command_supported,
                "supported_commands": sorted(r.adapter.commands),
                "command_interval_seconds": r.decision.interval,
            }
        if self.key == "execution":
            return {
                "error": r.error,
                "requested": r.recovery.requested,
                "auto_pending": r.recovery.restore_pending,
                "retry_after": r.recovery.ready_after,
                "invalid_fields": r.invalid,
                "verified_effective_command": r.recovery.verified,
                "command_supported": r.command_supported,
                "telemetry_interval_seconds": r.interval,
            }
        return None
