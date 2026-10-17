from custom_components.hems.contract import parse_contract
from custom_components.hems.output_presentation import decision_attributes, display_name, evaluate_expression, load_attributes, output_specs
from custom_components.hems.protocol import parse_response


def _contract():
    return parse_contract(
        {
            "contract": "test",
            "contract_version": 1,
            "exchange": {"method": "POST", "path": "/battery", "auth_header": "X"},
            "inputs": {},
            "outputs": {
                "decision": {
                    "entity": "sensor", "state_from": "action", "values": ["observe"],
                    "attributes": {"power_kw": {}, "command_interval_seconds": {}, "fresh": {}, "notice": {"type": "string"}},
                    "names": {"en": "Decision", "sv": "Beslut"}, "unique_id": "decision",
                    "extra_entities": {
                        "fresh": {"entity": "binary_sensor", "from": "attributes.fresh", "names": {"en": "Fresh"}, "unique_id": "fresh"},
                        "unsafe": {"entity": "sensor", "from": "attributes.__class__", "names": {"en": "Unsafe"}, "unique_id": "unsafe"},
                    },
                },
                "loads": {"entry": {"reason": {}, "power_w": {}, "internal": {}}, "entity_per_entry": {"attributes_from_entry": ["reason", "power_w", "unknown"]}},
                "connection": {"entity": "sensor", "local": True, "expression": "connected if exchange_age < 10 else disconnected", "names": {"en": "Connection"}, "unique_id": "connection"},
            },
        }
    )


def test_output_factory_uses_declared_safe_entities_only():
    specs = output_specs(_contract())
    assert [(spec.key, spec.entity, spec.source) for spec in specs] == [
        ("decision", "sensor", "action"),
        ("fresh", "binary_sensor", "attributes.fresh"),
        ("connection", "sensor", "expression"),
    ]


def test_load_presentation_fields_are_contract_whitelisted():
    assert load_attributes(_contract()) == ("reason", "power_w")


def test_contract_name_uses_home_assistant_language():
    spec = output_specs(_contract())[0]
    runtime = type("Runtime", (), {"hass": type("Hass", (), {"config": type("Config", (), {"language": "sv-SE"})()})()})()
    assert display_name(runtime, spec) == "Beslut"


def test_output_expressions_are_evaluated_without_running_contract_code():
    assert evaluate_expression("power_kw * 1000", {"power_kw": 2.5}) == 2500
    assert evaluate_expression("connected if exchange_age < 150 else warning", {"exchange_age": 151}) == "warning"
    contract = _contract()
    decision = type("Decision", (), {"presentation": {"power_kw": 2.5, "command_interval_seconds": 20}, "received_at": 100})()
    assert decision_attributes(contract, decision, 110)["power_kw"] == 2.5


def test_local_output_expression_owns_connection_labels_and_thresholds():
    # Neither the thresholds nor the labels appear in client code: the
    # expression is supplied by the contract and uses only the local fact.
    expression = _contract().output("connection")["expression"]
    assert evaluate_expression(expression, {"exchange_age": 5}) == "connected"
    assert evaluate_expression(expression, {"exchange_age": 12}) == "disconnected"


def test_declared_future_response_attribute_is_preserved_without_client_list():
    decision = parse_response({"action": "observe", "notice": "Service message"}, 100, _contract())
    assert decision.presentation["notice"] == "Service message"
