"""Contract-derived telemetry configuration tests without Home Assistant."""

import json

import pytest

from custom_components.hems.contract import bundled_contract_path, load_bundled_contract, parse_contract
from custom_components.hems.local_transformations import TransformationError, evaluate
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


def test_legacy_options_do_not_raise_repairs_after_upgrade():
    """a9 selections remain valid until Options next saves their new names."""
    contract = load_bundled_contract()
    options = {
        "soc_entity": "sensor.soc",
        "grid_entity": "sensor.grid",
        "battery_entity": "sensor.battery",
        "solar_entities": ["sensor.pv"],
    }
    states = {
        "sensor.soc": SelectedState("sensor.soc", "sensor", "battery", "%"),
        "sensor.grid": SelectedState("sensor.grid", "sensor", "power", "W"),
        "sensor.battery": SelectedState("sensor.battery", "sensor", "power", "W"),
        "sensor.pv": SelectedState("sensor.pv", "sensor", "power", "W"),
    }
    assert not invalid_configured_inputs(contract, options, states.get)


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


def test_interim_input_safety_keeps_invalid_ev_power_out_of_the_request():
    contract = load_bundled_contract()
    options = {
        option_key("battery_soc"): "sensor.soc",
        option_key("grid_power"): "sensor.grid",
        option_key("battery_power"): "sensor.battery",
        option_key("solar_sources"): ["sensor.pv"],
        option_key("ev_power"): "sensor.ev_power",
    }
    observations = {
        "sensor.soc": Observation(50, "%", 100),
        "sensor.grid": Observation(2, "kW", 100),
        "sensor.battery": Observation(500, "W", 100),
        "sensor.pv": Observation(1, "kW", 100),
        "sensor.ev_power": Observation(-2, "kW", 100),
    }
    sample, invalid = collect_contract(options, observations.get, 110, contract)
    # Temporary 0.2.0a1 guard requested by the contract owner. It can be
    # removed when the contract declares an input min/range schema.
    assert "ev_power_w" not in sample
    assert invalid == ["ev_power_w"]


def test_transformations_follow_a_renamed_contract_input_not_client_semantics():
    """A safe future input can define its own unit/sign transformation."""
    data = json.loads(bundled_contract_path().read_text(encoding="utf-8"))
    data["inputs"] = {
        "future_meter": {
            "field": "future_value",
            "required": True,
            "domain": "sensor",
            "units": ["quanta"],
            "options": ["invert"],
            "stale_after_s": 60,
        }
    }
    data["rules"] = {
        "scale": {
            "applies_to": ["future_meter"],
            "expression": "value * 10 if unit == 'quanta' else value",
        },
        "invert": {
            "applies_to": ["future_meter"],
            "expression": "-value if option.invert else value",
        },
    }
    contract = parse_contract(data)
    sample, invalid = collect_contract(
        {
            option_key("future_meter"): "sensor.future",
            option_flag_key("future_meter", "invert"): True,
        },
        lambda _entity: Observation(3, "quanta", 100),
        110,
        contract,
    )
    assert sample == {"future_value": -30}
    assert not invalid


def test_local_expression_grammar_cannot_execute_contract_code():
    with pytest.raises(TransformationError):
        evaluate("__import__('os').system('never')", value=1)
