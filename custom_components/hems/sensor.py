"""Decision and telemetry status. Measured power is never inferred from commands."""

import time
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .dynamic_entities import HemsOutputSensor, OutputTracker
from .entity import HemsEntity
from .output_presentation import ExpressionError, OutputSpec, decision_attributes, display_name, evaluate_expression, load_attributes, output_specs

EXECUTION_STATES = [
    "starting",
    "observing",
    "stopped",
    "observation_error",
]


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    output_tracker = OutputTracker()
    load_fields = load_attributes(runtime.contract)
    output_entities = []

    def sync_outputs():
        decision = runtime.decision
        if decision is None:
            return
        # Runtime subscribers are stored without an ordering guarantee. Update
        # the tracker before asking each existing entity to publish, otherwise
        # a load sensor can show the previous EV action/attributes until the
        # next timer tick.
        new_entries = output_tracker.update(decision.loads)
        if new_entries:
            new_entities = [HemsOutputSensor(runtime, output_tracker, item, load_fields) for item in new_entries]
            output_entities.extend(new_entities)
            async_add_entities(new_entities)
        for output_entity in output_entities:
            if output_entity.hass is not None:
                output_entity.async_write_ha_state()

    entry.async_on_unload(runtime.subscribe(sync_outputs))
    async_add_entities(
        [
            ContractOutputSensor(runtime, spec)
            for spec in output_specs(runtime.contract)
            if spec.entity == "sensor"
        ]
        + [ExecutionDiagnostic(runtime)]
    )


class ContractOutputSensor(HemsEntity, SensorEntity):
    _unrecorded_attributes = frozenset({"loads"})

    def __init__(self, runtime, spec: OutputSpec):
        super().__init__(runtime, spec.unique_id)
        self.spec = spec
        self._attr_name = display_name(runtime, spec)
        for attr in ("icon", "device_class", "state_class", "entity_category"):
            value = spec.definition.get(attr)
            if isinstance(value, str):
                setattr(self, f"_attr_{attr if attr != 'unit' else 'native_unit_of_measurement'}", value)
        unit = spec.definition.get("unit")
        if isinstance(unit, str):
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        r = self.runtime
        if self.spec.source == "action":
            return r.decision.action if r.decision else None
        if self.spec.source.startswith("attributes."):
            if not r.decision:
                return None
            attribute = self.spec.source.removeprefix("attributes.")
            return decision_attributes(r.contract, r.decision, time.time()).get(attribute)
        try:
            # Local facts are supplied by the client; their meaning and every
            # resulting state are owned by the contract expression.
            exchange_age = None if r.last_success is None else time.time() - r.last_success
            return evaluate_expression(self.spec.definition["expression"], {"exchange_age": exchange_age})
        except (ExpressionError, KeyError):
            return None

    @property
    def extra_state_attributes(self):
        r = self.runtime
        if self.spec.source == "action" and r.decision:
            return {
                **decision_attributes(r.contract, r.decision, time.time()),
                "loads": [dict(load) for load in r.decision.loads] if r.decision.loads is not None else None,
                "ev_chargers": [dict(charger) for charger in r.decision.ev_chargers] if r.decision.ev_chargers is not None else None,
            }
        return None


class ExecutionDiagnostic(HemsEntity, SensorEntity):
    """Client diagnostic, deliberately outside the HEMS output contract."""

    def __init__(self, runtime):
        super().__init__(runtime, "execution")
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = EXECUTION_STATES

    @property
    def native_value(self):
        return self.runtime.status

    @property
    def extra_state_attributes(self):
        r = self.runtime
        return {
            "error": r.error,
            "telemetry_enabled": r.telemetry_enabled,
            "invalid_fields": r.invalid,
            "stale_fields": r.measurements.get("stale", []),
            "telemetry_interval_seconds": r.interval,
        }
