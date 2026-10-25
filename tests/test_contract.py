import json
from pathlib import Path

import pytest

from custom_components.hems.contract import (
    ContractError,
    ContractStore,
    bundled_contract_path,
    load_bundled_contract,
    parse_contract,
    parse_contract_json,
)


def bundled_data():
    return json.loads(bundled_contract_path().read_text(encoding="utf-8"))


def authoritative_contract_path() -> Path:
    """Return the co-maintainer-owned source contract in this checkout."""
    return Path(__file__).resolve().parents[1] / "contract" / "hems-contract.json"


def test_packaged_contract_matches_the_authoritative_contract_exactly():
    """A HACS installation must ship the same contract documented in the repo."""
    assert bundled_contract_path().read_bytes() == authoritative_contract_path().read_bytes()


def test_loads_authoritative_bundled_contract_as_read_only_data():
    contract = load_bundled_contract()
    assert contract.name == "hems-battery-exchange"
    assert contract.version == 1
    assert contract.input("battery_soc").units == ("%",)
    assert contract.output("decision")["state_from"] == "action"
    assert contract.exchange_policy.path == "/battery"
    assert contract.exchange_policy.cadence.every_s == 20
    assert contract.exchange_policy.cadence.min_spacing_s == 20
    assert contract.exchange_policy.cadence.backoff_after_failure_s == 60
    assert contract.exchange_policy.max_response_bytes == 65536
    assert contract.request_constants.app_version == "ha-hems/<version>"
    assert contract.stale_on_invalid_sources
    with pytest.raises(TypeError):
        contract.raw["contract"] = "other"


def test_unknown_additive_fields_are_preserved_without_interpretation():
    data = bundled_data()
    data["inputs"]["future"] = {
        "field": "future_value",
        "required": False,
        "domain": "sensor",
        "unit": "x",
        "future_rule": {"expression": "__import__('os').system('never')"},
    }
    contract = parse_contract(data)
    assert contract.input("future").field == "future_value"
    assert contract.input("future").definition["future_rule"]["expression"].startswith("__import__")


@pytest.mark.parametrize(
    "change, error",
    [
        (lambda data: data.pop("exchange"), "invalid_exchange"),
        (lambda data: data["exchange"].update(method="GET"), "invalid_exchange_method"),
        (lambda data: data["exchange"].update(path="battery"), "invalid_exchange_path"),
        (lambda data: data["inputs"]["battery_soc"].update(required="yes"), "invalid_input_battery_soc_required"),
        (lambda data: data["outputs"]["decision"].pop("attributes"), "invalid_decision_attributes"),
        (lambda data: data["outputs"]["decision"]["attributes"].pop("power_kw"), "missing_decision_power_kw"),
    ],
)
def test_rejects_structurally_unusable_contract(change, error):
    data = bundled_data()
    change(data)
    with pytest.raises(ContractError, match=error):
        parse_contract(data)


@pytest.mark.parametrize(
    "change, error",
    [
        (lambda data: data["exchange"].update(max_response_bytes=0), "invalid_exchange_max_response_bytes"),
        (lambda data: data["exchange"]["cadence"].update(every_s=0), "invalid_exchange_cadence_every_s"),
        (lambda data: data["exchange"]["cadence"].update(min_spacing_s=False), "invalid_exchange_cadence_min_spacing_s"),
        (lambda data: data["exchange"]["cadence"].update(also_at_quarter_hour="yes"), "invalid_exchange_cadence_also_at_quarter_hour"),
    ],
)
def test_rejects_unsafe_exchange_policy(change, error):
    data = bundled_data()
    change(data)
    with pytest.raises(ContractError, match=error):
        parse_contract(data)


@pytest.mark.parametrize(
    "change, error",
    [
        (lambda data: data["rules"]["constants"].update(heartbeat="false"), "invalid_request_heartbeat"),
        (lambda data: data["rules"]["constants"].update(app_version="bad\nvalue"), "invalid_request_app_version"),
    ],
)
def test_rejects_non_literal_request_constants(change, error):
    data = bundled_data()
    change(data)
    with pytest.raises(ContractError, match=error):
        parse_contract(data)


def test_invalid_json_does_not_become_a_contract():
    with pytest.raises(ContractError, match="invalid_contract_json"):
        parse_contract_json("{broken")


def test_store_keeps_last_valid_contract_after_a_bad_future_download():
    original = load_bundled_contract()
    store = ContractStore(original)
    malformed = bundled_data()
    malformed["contract_version"] = 0
    assert not store.replace(malformed)
    assert store.current is original
    assert store.last_error == "invalid_contract_version"
    assert store.replace(bundled_data())
    assert store.current.version == 1
    assert store.last_error is None


def test_store_can_accept_downloaded_json_without_executing_it():
    store = ContractStore()
    data = bundled_data()
    data["rules"]["future"] = {"expression": "raise RuntimeError('never run')"}
    assert store.replace_json(json.dumps(data))
    assert store.current.raw["rules"]["future"]["expression"].startswith("raise")
