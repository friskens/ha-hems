"""Informational HEMS binary sensors; none of them control equipment."""

import time

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import REQUIRED_FIELDS
from .entity import HemsEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    async_add_entities([MeasurementsReady(runtime, "measurements"), DecisionFresh(runtime, "decision_fresh")])


class MeasurementsReady(HemsEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return all(key in self.runtime.measurements for key in REQUIRED_FIELDS)


class DecisionFresh(HemsEntity, BinarySensorEntity):
    """Whether a local automation may still use the last HEMS decision."""

    @property
    def is_on(self):
        decision = self.runtime.decision
        return bool(decision and 0 <= time.time() - decision.received_at < 90)
