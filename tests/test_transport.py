import json
import pytest

from custom_components.hems.protocol import ProtocolError
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


async def test_header_only_no_redirect_or_heartbeat():
    session = Session()
    decision = await Client(session, "https://example.com/battery", "test-secret").exchange(
        {"soc": 50, "api_key": "must-not-send", "ev_soc_pct": 80}, lambda: 100
    )
    assert decision.action == "pause"
    assert session.kwargs["headers"] == {"X-Api-Key": "test-secret"}
    assert session.kwargs["allow_redirects"] is False
    assert "api_key" not in session.kwargs["json"]
    assert session.kwargs["json"]["heartbeat"] is False
    assert session.kwargs["json"]["ev_soc_pct"] == 80


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
