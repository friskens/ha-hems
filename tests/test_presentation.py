"""Pure presentation tests; no Home Assistant installation is required."""

from custom_components.hems.presentation import (
    connection_state,
    decision_is_fresh,
    followed_status,
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


def test_connection_states_and_freshness_are_conservative():
    assert connection_state(1000, 1100) == "connected"
    assert connection_state(1000, 1150) == "warning"
    assert connection_state(1000, 1600) == "disconnected"
    assert not decision_is_fresh(1100, 1000)
    assert decision_is_fresh(1000, 1089)
    assert not decision_is_fresh(1000, 1090)


def test_followed_status_never_claims_a_vendor_command_was_applied():
    waiting = followed_status(
        action="charge", received_at=1000, observation=True, observed_at=1001, now=1050
    )
    assert waiting.state == "waiting"
    unknown = followed_status(
        action="charge", received_at=1000, observation=None, observed_at=None, now=1050
    )
    assert (unknown.state, unknown.reason) == ("waiting", "grace_period")
    mismatch = followed_status(
        action="charge",
        received_at=1190,
        decision_since=1000,
        observation=False,
        observed_at=1190,
        now=1200,
    )
    assert mismatch.state == "not_following"
