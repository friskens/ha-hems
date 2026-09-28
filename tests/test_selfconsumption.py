import pytest

from custom_components.hems.protocol import ProtocolError, parse_response


@pytest.mark.parametrize("power", [0, 1.3, 11])
def test_selfconsumption_preserves_action_and_ceiling(power):
    decision = parse_response({"action": "selfconsumption", "power_kw": power}, 100)
    assert decision.effective == ("selfconsumption", power * 1000)


def test_missing_cap_is_not_invented():
    with pytest.raises(ProtocolError, match="invalid_power_kw"):
        parse_response({"action": "selfconsumption"}, 100)
