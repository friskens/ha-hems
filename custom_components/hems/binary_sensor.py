"""Informational HEMS binary sensors; none of them control equipment."""

import time

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import HemsEntity
from .output_presentation import (
    ExpressionError,
    decision_attributes,
    display_name,
    evaluate_expression,
    output_specs,
)


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    entities = [MeasurementsReady(runtime, "measurements")]
    entities.extend(ContractBinarySensor(runtime, spec) for spec in output_specs(runtime.contract) if spec.entity == "binary_sensor")
    async_add_entities(entities)


class MeasurementsReady(HemsEntity, BinarySensorEntity):
    @property
    def is_on(self):
        stale = set(self.runtime.measurements.get("stale", ()))
        required_fields = {
            input_spec.field
            for input_spec in self.runtime.contract.inputs.values()
            if input_spec.required
        }
        return all(
            field in self.runtime.measurements and field not in stale
            for field in required_fields
        )


class ContractBinarySensor(HemsEntity, BinarySensorEntity):
    """Whether a local automation may still use the last HEMS decision."""

    def __init__(self, runtime, spec):
        super().__init__(runtime, spec.unique_id)
        self.spec = spec
        self._attr_name = display_name(runtime, spec)

    @property
    def is_on(self):
        decision = self.runtime.decision
        if not decision:
            return None
        if self.spec.source.startswith("attributes."):
            return bool(decision_attributes(self.runtime.contract, decision, time.time()).get(self.spec.source.removeprefix("attributes.")))
        if self.spec.source == "action":
            return bool(decision.action)
        if self.spec.source == "expression":
            try:
                return bool(
                    evaluate_expression(
                        self.spec.definition["expression"],
                        {"exchange_age": time.time() - self.runtime.last_success},
                    )
                )
            except ExpressionError:
                return None
        return None
