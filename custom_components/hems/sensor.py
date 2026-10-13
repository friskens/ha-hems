"""Decision and execution status. Measured power is not inferred from commands."""

import time
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .dynamic_entities import HemsOutputSensor, OutputTracker
from .entity import HemsEntity

EXECUTION_STATES = [
    "starting",
    "observing",
    "stopped",
    "observation_error",
    "applying",
    "settings_verified",
    "adapter_failed",
    "verification_failed",
]


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    output_tracker = OutputTracker()

    def sync_outputs():
        decision = runtime.decision
        if decision is None:
            return
        new_entries = output_tracker.update(decision.loads)
        if new_entries:
            async_add_entities([HemsOutputSensor(runtime, output_tracker, item) for item in new_entries])

    entry.async_on_unload(runtime.subscribe(sync_outputs))
    async_add_entities(
        [
            HemsSensor(runtime, key)
            for key in ("decision", "execution", "connection", "ev_soc", "power_target", "command_interval")
        ]
    )


class HemsSensor(HemsEntity, SensorEntity):
    _unrecorded_attributes = frozenset({"loads"})

    def __init__(self, runtime, key):
        super().__init__(runtime, key)
        self.key = key
        if key == "ev_soc":
            self._attr_native_unit_of_measurement = "%"
            self._attr_device_class = SensorDeviceClass.BATTERY
        elif key in {"decision", "execution", "connection"}:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = {
                "execution": EXECUTION_STATES,
                "connection": ["connected", "warning", "disconnected"],
            }.get(key)
        elif key == "power_target":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = "W"
        elif key == "command_interval":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = "s"

    @property
    def native_value(self):
        r = self.runtime
        if self.key == "decision":
            return r.decision.action if r.decision else None
        if self.key == "power_target":
            return r.decision.power_kw * 1000 if r.decision else None
        if self.key == "command_interval":
            return r.decision.interval if r.decision else None
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
                "loads": [dict(load) for load in r.decision.loads] if r.decision.loads is not None else None,
                "command_supported": r.command_supported,
                "supported_commands": sorted(r.adapter.commands),
                "command_interval_seconds": r.decision.interval,
                "power_w": r.decision.power_kw * 1000,
            }
        if self.key == "execution":
            return {
                "error": r.error,
                "requested": r.recovery.requested,
                "invalid_fields": r.invalid,
                "verified_effective_command": r.recovery.verified,
                "failed_effective_command": r.recovery.failed,
                "adapter_receipt": r.last_receipt,
                "command_supported": r.command_supported,
                "telemetry_interval_seconds": r.interval,
            }
        return None
