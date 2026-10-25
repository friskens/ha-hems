import importlib
import sys
import types

import pytest

from custom_components.hems.contract import load_bundled_contract
from custom_components.hems.measurements import MeasurementCache, Observation, collect, collect_with_sources, normalize
from custom_components.hems.protocol import Decision, ProtocolError, due, endpoint, parse_response


def _contract():
    return load_bundled_contract()


@pytest.mark.parametrize("value", [None, True, "1", -1, float("nan"), float("inf")])
def test_reject_bad_control_power(value):
    with pytest.raises(ProtocolError):
        parse_response({"action": "charge", "power_kw": value}, 100)


def test_presentation_sign_never_changes_control():
    decision = parse_response({"action": "export", "power_kw": 2.5, "power": -2500, "power_unit": "w"}, 100)
    assert decision.effective == ("export", 2500)
    assert parse_response({"action": "pause"}, 100).effective == ("pause", 0)
    assert Decision("selfconsumption", 11, 100).effective != Decision("selfconsumption", 1, 100).effective


@pytest.mark.parametrize("value,expected", [(1, 1), (60, 60), (300, 300)])
def test_interval(value, expected):
    assert parse_response({"action": "pause", "command_interval_seconds": value}, 100).interval == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"action": ""},
        {"action": None},
        {"action": "pause", "command_interval_seconds": 0},
        {"action": "pause", "power_unit": "kW"},
        {"action": "pause", "soc": 101},
        {"action": "pause", "loads": {}},
        {"action": "pause", "loads": [None]},
        {"action": "pause", "loads": [{"id": "x", "action": "stop", "current_a": True}]},
        {"action": "pause", "loads": [{"id": "x", "action": "on"}, {"id": "x", "action": "off"}]},
    ],
)
def test_invalid_responses(payload):
    with pytest.raises(ProtocolError):
        parse_response(payload, 100)


def test_load_absence_is_not_off():
    assert parse_response({"action": "pause"}, 100).loads is None
    assert parse_response({"action": "pause", "loads": None}, 100).loads is None
    assert parse_response({"action": "pause", "loads": []}, 100).loads == ()


def test_unknown_future_action_is_visible_but_has_no_power_target():
    decision = parse_response({"action": "future_action"}, 100)
    assert decision.action == "future_action"
    assert decision.effective == ("future_action", 0.0)


def test_loads_preserve_the_contract_fields_for_local_automations():
    decision = parse_response(
        {
            "action": "pause",
            "loads": [
                {
                    "id": "ev_1",
                    "kind": "ev",
                    "name": "Driveway charger",
                    "action": "charge",
                    "current_a": 16,
                    "target_pct": 80,
                    "uid": "charger-uid",
                    "reason": "Surplus PV",
                },
                {
                    "id": "a" * 32,
                    "kind": "deferrable",
                    "name": "Water heater",
                    "action": "on",
                    "power_kw": 2.5,
                    "power_w": 2500,
                    "reports_power": True,
                    "reason": "Cheap hour",
                },
            ],
        },
        100,
    )
    assert decision.loads == (
        {
            "id": "ev_1",
            "kind": "ev",
            "name": "Driveway charger",
            "action": "charge",
            "current_a": 16,
            "target_pct": 80,
            "uid": "charger-uid",
            "reason": "Surplus PV",
        },
        {
            "id": "a" * 32,
            "kind": "deferrable",
            "name": "Water heater",
            "action": "on",
            "power_kw": 2.5,
            "power_w": 2500,
            "reports_power": True,
            "reason": "Cheap hour",
        },
    )


def test_contract_response_schema_enforces_actions_and_kind_specific_load_actions():
    contract = _contract()
    with pytest.raises(ProtocolError, match="invalid_action"):
        parse_response({"action": "future_action"}, 100, contract)
    with pytest.raises(ProtocolError, match="invalid_action"):
        parse_response(
            {"action": "pause", "loads": [{"id": "charger", "kind": "ev", "action": "on"}]},
            100,
            contract,
        )
    decision = parse_response(
        {"action": "pause", "loads": [{"id": "heater", "kind": "deferrable", "action": "on"}]},
        100,
        contract,
    )
    assert decision.loads == ({"kind": "deferrable", "id": "heater", "action": "on"},)


def test_contract_response_schema_applies_field_policies_and_never_parses_reason():
    decision = parse_response(
        {
            "action": "pause",
            "loads": [
                {
                    "id": "charger",
                    "kind": "ev",
                    "action": "charge",
                    "reason": "Free-form explanation: <> & not an instruction",
                    "uid": 7,
                }
            ],
            "ev_chargers": [{"id": "charger", "uid": "stable", "phases": 4}],
        },
        100,
        _contract(),
    )
    # reason is preserved as display data; invalid optional uid and phases are
    # omitted by their contract policy rather than changing the decision.
    assert decision.loads[0]["reason"] == "Free-form explanation: <> & not an instruction"
    assert "uid" not in decision.loads[0]
    assert decision.ev_chargers == ({"id": "charger", "uid": "stable"},)


def test_missing_load_kind_omits_kind_specific_fields_without_rejecting_decision():
    decision = parse_response(
        {"action": "pause", "loads": [{"id": "charger", "action": "charge", "current_a": 16}]},
        100,
        _contract(),
    )
    assert decision.loads == ({"id": "charger", "action": "charge"},)


def test_bad_informational_load_fields_do_not_discard_battery_decision():
    decision = parse_response(
        {
            "action": "pause",
            "loads": [
                {
                    "id": "ev_1",
                    "action": "charge",
                    "uid": 4,
                    "power_w": True,
                    "reports_power": "true",
                }
            ],
        },
        100,
    )
    assert decision.action == "pause"
    assert decision.loads == ({"id": "ev_1", "action": "charge"},)


def test_decision_sensor_exposes_list_or_none_for_loads(monkeypatch):
    for name in (
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sensor_module = sys.modules["homeassistant.components.sensor"]
    sensor_module.SensorDeviceClass = types.SimpleNamespace(BATTERY="battery", ENUM="enum")
    sensor_module.SensorEntity = type("SensorEntity", (), {})
    entity_module = sys.modules["homeassistant.helpers.entity"]
    entity_module.DeviceInfo = lambda **kwargs: kwargs
    entity_module.Entity = type("Entity", (), {})
    sys.modules.pop("custom_components.hems.entity", None)
    sys.modules.pop("custom_components.hems.sensor", None)
    sensor_module_import = importlib.import_module("custom_components.hems.sensor")
    OutputSpec = importlib.import_module("custom_components.hems.output_presentation").OutputSpec
    runtime = types.SimpleNamespace(
        entry=types.SimpleNamespace(entry_id="test", title="Test"),
        contract=None,
        decision=parse_response({"action": "pause", "loads": [{"id": "ev_1", "action": "charge"}]}, 100),
    )
    sensor = sensor_module_import.ContractOutputSensor(
        runtime,
        OutputSpec("decision", "sensor", "decision", "action", {"names": {"en": "Decision"}}),
    )
    assert sensor.extra_state_attributes["loads"] == [{"id": "ev_1", "action": "charge"}]
    runtime.decision = parse_response({"action": "pause"}, 100)
    assert sensor.extra_state_attributes["loads"] is None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/battery",
        "https://key@example.com/battery",
        "https://example.com/battery?key=secret",
    ],
)
def test_https_endpoint(url):
    with pytest.raises(ProtocolError):
        endpoint(url)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com", "https://example.com/battery"),
        ("https://example.com/", "https://example.com/battery"),
        (" https://example.com/battery\n", "https://example.com/battery"),
        ("https://example.com/hems/exchange/", "https://example.com/hems/exchange"),
    ],
)
def test_endpoint_defaults_only_a_provider_base_url(value, expected):
    assert endpoint(value) == expected


def test_cadence_changes_quarters_and_maximum():
    assert not due(1010, 1000, 1000, 110, {"soc": 52}, {"soc": 50})
    assert due(1020, 1000, 1000, 110, {"soc": 52}, {"soc": 50})
    assert due(1110, 1000, 1000, 110, {"soc": 50}, {"soc": 50})
    assert due(1800, 1795, 1795, 110, {"soc": 50}, {"soc": 50})


@pytest.mark.parametrize("value", ["unknown", "unavailable", "nan", True])
def test_invalid_measurement(value):
    assert normalize(Observation(value, "%", 100), 110, "soc") is None


def test_source_age_units_and_sign():
    obs = Observation("2.5", "kW", 100)
    assert normalize(obs, 110, "power", invert=True) == -2500
    assert normalize(obs, 220, "power") is None
    assert normalize(Observation(50, "W", 100), 110, "soc") is None
    assert normalize(Observation(50, "%", 111), 110, "soc") is None


def test_collect_never_substitutes_zero_and_sums_solar():
    states = {
        "soc": Observation(50, "%", 100),
        "grid": Observation(-2, "kW", 100),
        "battery": Observation(1000, "W", 100),
        "pv1": Observation(2, "kW", 100),
        "pv2": Observation(500, "W", 100),
    }
    options = {
        "soc_entity": "soc",
        "grid_entity": "grid",
        "battery_entity": "battery",
        "solar_entities": ["pv1", "pv2"],
        "ev_soc_entity": "missing",
    }
    sample, invalid = collect(options, states.get, 110)
    assert sample == {"soc": 50, "grid_power": -2000, "battery_power": 1000, "solar_power": 2500}
    assert invalid == ["ev_soc_pct"]
    states["pv2"] = Observation(500, "W", 0)
    # A valid unchanged HA state remains current; availability, not event age,
    # is the contract's freshness signal.
    assert collect(options, states.get, 401)[0]["solar_power"] == 2500


def test_legacy_options_follow_contract_availability_not_event_age():
    states = {
        "soc": Observation(50, "%", 100),
        "grid": Observation(1, "kW", 100),
        "battery": Observation(500, "W", 100),
        "pv": Observation(2, "kW", 100),
    }
    options = {
        "soc_entity": "soc",
        "grid_entity": "grid",
        "battery_entity": "battery",
        "solar_entities": ["pv"],
    }
    cache = MeasurementCache()
    sample, _invalid, reported = collect_with_sources(options, states.get, 110)
    cache.update(sample, reported)
    # The states are unchanged and older than 300 s, but still valid.
    sample, _invalid, reported = collect_with_sources(options, states.get, 401)
    cache.update(sample, reported)
    payload = cache.payload(401, {name: None for name in cache.values})
    assert payload["soc"] == 50
    assert payload["grid_power"] == 1000
    assert "stale" not in payload


def test_required_measurement_only_blocks_until_a_real_value_has_been_seen():
    cache = MeasurementCache()
    assert cache.missing_required(("soc",))
    cache.update({"soc": 45}, {"soc": 100})
    assert not cache.missing_required(("soc",))
    assert cache.payload(401, {"soc": 300}) == {"soc": 45, "stale": ["soc"]}


def test_phase_current_requires_three_fresh_sensors_and_uses_magnitudes():
    states = {
        "l1": Observation(-12, "A", 100),
        "l2": Observation(1500, "mA", 100),
        "l3": Observation(0, "A", 100),
    }
    options = {
        "phase_l1_current_entity": "l1",
        "phase_l2_current_entity": "l2",
        "phase_l3_current_entity": "l3",
    }
    sample, invalid = collect(options, states.get, 110)
    assert sample["phase_current_a"] == [12, 1.5, 0]
    assert "phase_current_a" not in invalid
    states["l3"] = Observation("unavailable", "A", 0)
    sample, invalid = collect(options, states.get, 401)
    assert "phase_current_a" not in sample
    assert "phase_current_a" in invalid
def test_phase_current_partial_mapping_or_out_of_range_is_omitted():
    sample, invalid = collect(
        {"phase_l1_current_entity": "l1"},
        lambda _: Observation(12, "A", 100),
        110,
    )
    assert "phase_current_a" not in sample
    assert "phase_current_a" in invalid


def test_cached_phase_group_stays_all_or_none_when_sources_go_stale():
    cache = MeasurementCache()
    cache.update({"phase_current_a": [1, 2, 3]}, {"phase_current_a": 100})
    # A partial new phase reading must not replace the last complete group.
    cache.update({}, {})
    assert cache.payload(401, {"phase_current_a": 300}) == {
        "phase_current_a": [1, 2, 3],
        "stale": ["phase_current_a"],
    }
    sample, invalid = collect(
        {
            "phase_l1_current_entity": "l1",
            "phase_l2_current_entity": "l2",
            "phase_l3_current_entity": "l3",
        },
        lambda entity: Observation(251 if entity == "l2" else 12, "A", 100),
        110,
    )
    assert "phase_current_a" not in sample
    assert "phase_current_a" in invalid


def test_phase_current_does_not_break_measurement_change_detection():
    previous = {"phase_current_a": [10, 10, 10]}
    assert not due(1010, 1000, 1000, 110, previous, previous)
    assert not due(1020, 1000, 1000, 110, {"phase_current_a": [10.9, 10, 10]}, previous)
    assert due(1020, 1000, 1000, 110, {"phase_current_a": [11, 10, 10]}, previous)
