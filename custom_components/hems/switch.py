"""Persistent telemetry exchange switch; it never controls equipment."""

from homeassistant.components.switch import SwitchEntity

from .entity import HemsEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ControlSwitch(entry.runtime_data, "control")])


class ControlSwitch(HemsEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.runtime.telemetry_enabled

    async def async_turn_on(self, **kwargs):
        await self.runtime.request(True)

    async def async_turn_off(self, **kwargs):
        await self.runtime.request(False)
