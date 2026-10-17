import json
from pathlib import Path
import pytest

from custom_components.hems.contract import load_bundled_contract, parse_contract
from custom_components.hems.protocol import ProtocolError, due
from custom_components.hems.transport import AuthError, Client, TransportError


class Response:
    def __init__(self, status, body):
        self.status, self.body, self.content = status, body, self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def iter_chunked(self, size):
        for offset in range(0, len(self.body), size):
            yield self.body[offset : offset + size]


class Session:
    def __init__(self, status=200, body=None):
        self.response = Response(
            status, body if body is not None else json.dumps({"action": "pause"}).encode()
        )

    def post(self, url, **kwargs):
        self.url, self.kwargs = url, kwargs
        return self.response


def contract_with_exchange(**exchange):
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "contract" / "hems-contract.json").read_text(encoding="utf-8")
    )
    data["exchange"].update(exchange)
    return parse_contract(data)


async def test_header_only_no_redirect_or_heartbeat():
    session = Session()
    decision = await Client(session, "https://example.com/battery", "test-secret").exchange(
        {"soc": 50, "api_key": "must-not-send", "ev_soc_pct": 80, "phase_current_a": [1, 2, 3]}, lambda: 100
    )
    assert decision.action == "pause"
    assert session.kwargs["headers"] == {"X-Api-Key": "test-secret"}
    assert session.kwargs["allow_redirects"] is False
    assert "api_key" not in session.kwargs["json"]
    assert session.kwargs["json"]["heartbeat"] is False
    assert session.kwargs["json"]["ev_soc_pct"] == 80
    assert session.kwargs["json"]["phase_current_a"] == [1, 2, 3]


async def test_contract_allowlist_sends_known_telemetry_and_stale_only():
    session = Session()
    await Client(session, "https://example.com/battery", "test-secret", load_bundled_contract()).exchange(
        {
            "soc": 50,
            "grid_power": 1200,
            "load_power_w": 3000,  # Contract explicitly says not_sent.
            "unknown_future_field": 7,
            "stale": ["soc"],
        },
        lambda: 100,
    )
    assert session.kwargs["json"]["soc"] == 50
    assert session.kwargs["json"]["stale"] == ["soc"]
    assert "load_power_w" not in session.kwargs["json"]
    assert "unknown_future_field" not in session.kwargs["json"]


async def test_contract_controls_base_path_header_and_literal_constants():
    contract = contract_with_exchange(path="/contract-exchange", auth_header="X-Contract-Key")
    session = Session()
    await Client(session, "https://example.com", "test-secret", contract).exchange({}, lambda: 100)
    assert session.url == "https://example.com/contract-exchange"
    assert session.kwargs["headers"] == {"X-Contract-Key": "test-secret"}
    assert session.kwargs["json"]["heartbeat"] is False
    assert session.kwargs["json"]["app_version"] == "ha-hems/0.2.0a2"


async def test_contract_response_limit_is_enforced():
    contract = contract_with_exchange(max_response_bytes=10)
    with pytest.raises(ProtocolError, match="response_too_large"):
        await Client(Session(body=b"x" * 11), "https://example.com", "secret", contract).exchange({}, lambda: 100)


def test_contract_cadence_controls_every_spacing_and_quarter_boundary():
    cadence = contract_with_exchange(
        cadence={
            "every_s": 90,
            "also_at_quarter_hour": False,
            "min_spacing_s": 30,
            "backoff_after_failure_s": 45,
        }
    ).exchange_policy.cadence
    assert not due(1020, 1000, 1000, 20, {"soc": 51}, {"soc": 50}, cadence)
    assert due(1030, 1000, 1000, 20, {"soc": 51}, {"soc": 50}, cadence)
    assert not due(1800, 1795, 1795, 20, {"soc": 50}, {"soc": 50}, cadence)
    assert due(1090, 1060, 1000, 20, {"soc": 50}, {"soc": 50}, cadence)


@pytest.mark.parametrize(
    "status,exception", [(401, AuthError), (403, AuthError), (302, TransportError), (500, TransportError)]
)
async def test_status_sanitized(status, exception):
    with pytest.raises(exception) as error:
        await Client(Session(status, b"private-body"), "https://example.com/battery", "secret").exchange(
            {}, lambda: 100
        )
    assert "private-body" not in str(error.value)


@pytest.mark.parametrize("body", [b"x" * 65537, b"not json"], ids=["too_large", "invalid_json"])
async def test_response_limits(body):
    with pytest.raises(ProtocolError):
        await Client(Session(body=body), "https://example.com/battery", "secret").exchange({}, lambda: 100)
