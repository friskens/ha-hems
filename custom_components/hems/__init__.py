"""HEMS client for Home Assistant."""

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import PLATFORMS
from .runtime import Runtime


async def async_setup_entry(hass, entry):
    runtime = Runtime(hass, entry, async_get_clientsession(hass))
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await runtime.start()
    return True


async def async_unload_entry(hass, entry):
    await entry.runtime_data.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
