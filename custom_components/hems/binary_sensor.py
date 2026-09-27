"""Whether telemetry inputs permit control; optional EV data does not block it."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import REQUIRED_FIELDS
from .entity import HemsEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([MeasurementsReady(entry.runtime_data, "measurements", "Measurements ready")])


class MeasurementsReady(HemsEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return all(key in self.runtime.measurements for key in REQUIRED_FIELDS)
