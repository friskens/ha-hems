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


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/battery",
        "https://key@example.com/battery",
        "https://example.com/battery?key=secret",
        "https://example.com",
    ],
)
def test_https_endpoint(url):
    with pytest.raises(ProtocolError):
        endpoint(url)


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


def test_recovery_requires_auto_and_fresh_sequence():
    recovery = Recovery()
    recovery.request(True, 100)
    for stamp in (100, 130, 160):
        recovery.good(stamp)
    decision = Decision("pause", 0, 160)
    assert not recovery.can_resume(160, decision)
    recovery.restore_pending = False
    assert recovery.can_resume(160, decision)
    assert not recovery.can_resume(250, decision)
    recovery.fault(160, control=True)
    recovery.restore_pending = False
    for stamp in (400, 430, 460):
        recovery.good(stamp)
    assert not recovery.can_resume(459, Decision("pause", 0, 459))
    assert recovery.can_resume(460, Decision("pause", 0, 460))
    recovery.request(False, 460)
    assert not recovery.can_resume(460, decision)


def test_gap_resets_recovery_sequence():
    recovery = Recovery()
    recovery.good(100)
    recovery.good(230)
    assert recovery.good_count == 1


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
