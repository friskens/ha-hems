import importlib
import sys
import types

import pytest

from custom_components.hems.adapter import VerificationError, validate_receipt
from custom_components.hems.measurements import Observation, collect, normalize
from custom_components.hems.protocol import Decision, ProtocolError, due, endpoint, parse_response
from custom_components.hems.recovery import Recovery


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
        {"action": "unchanged"},
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
    HemsSensor = importlib.import_module("custom_components.hems.sensor").HemsSensor
    runtime = types.SimpleNamespace(
        entry=types.SimpleNamespace(entry_id="test", title="Test"),
        decision=parse_response({"action": "pause", "loads": [{"id": "ev_1", "action": "charge"}]}, 100),
        command_supported=True,
        adapter=types.SimpleNamespace(commands=set()),
    )
    sensor = HemsSensor(runtime, "decision")
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
    assert "solar_power" not in collect(options, states.get, 130)[0]


def test_recovery_tracks_requested_and_failed_effective_command():
    recovery = Recovery()
    recovery.request(True, 100)
    assert recovery.requested
    recovery.failed = ("pause", 0)
    assert recovery.failed == ("pause", 0)
    recovery.request(False, 460)
    assert not recovery.requested
    assert recovery.failed is None


def test_new_control_request_clears_adapter_outcomes():
    recovery = Recovery()
    recovery.verified = ("pause", 0)
    recovery.failed = ("export", 1000)
    recovery.failed_status = "adapter_failed"
    recovery.failed_error = "adapter_failed"
    recovery.request(True, 100)
    assert recovery.verified is None
    assert recovery.failed is None
    assert recovery.failed_status is None
    assert recovery.failed_error is None


def test_receipt_is_bound_to_request_and_fresh_readback():
    receipt = {
        "verified": True,
        "token": "nonce",
        "command": "pause",
        "power_w": 0,
        "readback_at": 105,
        "readback": {"mode": 3},
    }
    validate_receipt(receipt, "pause", 0, "nonce", 100, 110)
    for changes in (
        {"token": "old"},
        {"readback_at": 99},
        {"readback": {}},
        {"verified": False},
        {"power_w": 1000},
    ):
        with pytest.raises(VerificationError):
            validate_receipt({**receipt, **changes}, "pause", 0, "nonce", 100, 110)
