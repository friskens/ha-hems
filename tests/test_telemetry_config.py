"""Contract-derived telemetry configuration tests without Home Assistant."""

from custom_components.hems.contract import load_bundled_contract
from custom_components.hems.measurements import Observation, collect_contract
from custom_components.hems.telemetry_config import (
    SelectedState,
    defaults_for_contract,
    invalid_configured_inputs,
    option_flag_key,
    option_key,
    selection_errors,
)


def test_legacy_a9_options_have_contract_derived_defaults():
    contract = load_bundled_contract()
    defaults = defaults_for_contract(
        contract,
        {
            "soc_entity": "sensor.soc",
            "grid_entity": "sensor.grid",
            "solar_entities": ["sensor.pv_a", "sensor.pv_b"],
            "invert_grid_power": True,
        },
    )
    assert defaults[option_key("battery_soc")] == "sensor.soc"
    assert defaults[option_key("solar_sources")] == ["sensor.pv_a", "sensor.pv_b"]
    assert defaults[option_flag_key("grid_power", "invert")] is True
    assert option_key("load_power") not in defaults


def test_required_multiple_and_group_selection_validation():
    contract = load_bundled_contract()
    options = {
        option_key("battery_soc"): "sensor.soc",
        option_key("grid_power"): "sensor.grid",
        option_key("battery_power"): "sensor.battery",
        option_key("solar_sources"): ["sensor.pv"],
        option_key("grid_meter_current_l1"): "sensor.l1",
    }
    errors = selection_errors(contract, options)
    assert "solar_sources" not in errors
    assert errors["grid_meter_current_l1"] == "incomplete_group"
    assert errors["grid_meter_current_l2"] == "incomplete_group"
    assert errors["grid_meter_current_l3"] == "incomplete_group"


def test_invalid_configuration_is_structural_not_freshness_based():
    contract = load_bundled_contract()
    options = {
        option_key("battery_soc"): "sensor.soc",
        option_key("grid_power"): "sensor.grid",
        option_key("battery_power"): "sensor.battery",
        option_key("solar_sources"): ["sensor.pv"],
    }
    states = {
        "sensor.soc": SelectedState("sensor.soc", "sensor", "battery", "%"),
        "sensor.grid": SelectedState("sensor.grid", "sensor", "power", "W"),
        "sensor.battery": SelectedState("sensor.battery", "sensor", "power", "kW"),
        "sensor.pv": SelectedState("sensor.pv", "sensor", "power", "W"),
    }
    assert not invalid_configured_inputs(contract, options, states.get)
    states["sensor.grid"] = SelectedState("sensor.grid", "sensor", "energy", "kWh")
    assert invalid_configured_inputs(contract, options, states.get) == {"grid_power"}


def test_contract_options_collect_without_executing_contract_expressions():
    contract = load_bundled_contract()
    options = {
        option_key("battery_soc"): "sensor.soc",
        option_key("grid_power"): "sensor.grid",
        option_key("battery_power"): "sensor.battery",
        option_key("solar_sources"): ["sensor.pv_a", "sensor.pv_b"],
        option_flag_key("grid_power", "invert"): True,
    }
    observations = {
        "sensor.soc": Observation(50, "%", 100),
        "sensor.grid": Observation(2, "kW", 100),
        "sensor.battery": Observation(500, "W", 100),
        "sensor.pv_a": Observation(1, "kW", 100),
        "sensor.pv_b": Observation(250, "W", 100),
    }
    sample, invalid = collect_contract(options, observations.get, 110, contract)
    assert sample == {"soc": 50, "grid_power": -2000, "battery_power": 500, "solar_power": 1250}
    assert not invalid
