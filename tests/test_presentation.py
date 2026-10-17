"""Pure presentation tests; no Home Assistant installation is required."""

from custom_components.hems.presentation import (
    telemetry_inputs,
)


def test_telemetry_inputs_support_known_declarative_fields_only():
    inputs = telemetry_inputs(
        {
            "grid": {
                "field": "grid_power",
                "required": True,
                "domain": "sensor",
                "device_class": "power",
                "units": ["W", "kW"],
                "options": ["invert"],
            },
            "future": {"field": "future", "domain": "number"},
            "bad": {"field": 3, "domain": "sensor"},
        }
    )
    assert len(inputs) == 1
    assert inputs[0].key == "grid"
    assert inputs[0].units == ("W", "kW")
