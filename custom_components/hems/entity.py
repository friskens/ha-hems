"""Shared local entities; telemetry runs independently of dashboard subscribers."""

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, VERSION


class HemsEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime, key):
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            name=runtime.entry.title,
            manufacturer="Community",
            model="HEMS client",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self):
        self.async_on_remove(self.runtime.subscribe(self.async_write_ha_state))
