"""HTTPS client. No key in URLs, payloads, diagnostics, or exception strings."""

import asyncio
import json

import aiohttp

from .const import VERSION
from .protocol import ProtocolError, endpoint, parse_response


class TransportError(Exception):
    """Sanitized transport failure."""


class AuthError(TransportError):
    """Authentication rejected."""


class Client:
    def __init__(self, session, url, key, contract=None):
        self.session = session
        self._key = key
        self.contract = contract
        self._exchange = contract.exchange_policy if contract else None
        self.url = endpoint(url, self._exchange.path if self._exchange else "/battery")
        # The contract describes which telemetry names may cross this boundary.
        # It is data, not code: no contract expression is evaluated here.
        if contract is None:
            self._allowed_fields = frozenset(
                {"soc", "grid_power", "solar_power", "battery_power", "ev_power_w", "ev_soc_pct", "phase_current_a"}
            )
        else:
            self._allowed_fields = frozenset(
                input_.field
                for input_ in contract.inputs.values()
                if input_.definition.get("client_status") != "not_sent"
            )

    async def exchange(self, measurements, now):
        # The allowlist prevents callers from reintroducing credentials or
        # accidental HA state into the request. ``stale`` is a fixed protocol
        # marker, never an arbitrary field provided by the contract.
        payload = {
            key: value
            for key, value in measurements.items()
            if key in self._allowed_fields or key == "stale"
        }
        # The contract's constants are declarative literal values.  The only
        # substitution supported is its documented version marker; this is
        # deliberately not a general template language.
        constants = self.contract.request_constants if self.contract else None
        heartbeat = constants.heartbeat if constants else False
        app_version = constants.app_version if constants else "ha-hems/<version>"
        payload.update(heartbeat=heartbeat, app_version=app_version.replace("<version>", VERSION))
        try:
            async with asyncio.timeout(15):
                async with self.session.post(
                    self.url,
                    headers={(self._exchange.auth_header if self._exchange else "X-Api-Key"): self._key},
                    json=payload,
                    allow_redirects=False,
                ) as response:
                    if response.status in (401, 403):
                        raise AuthError("authentication_failed")
                    if response.status != 200:
                        raise TransportError(f"http_{response.status}")
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        raw.extend(chunk)
                        if len(raw) > (self._exchange.max_response_bytes if self._exchange else 65536):
                            raise ProtocolError("response_too_large")
                    try:
                        data = json.loads(raw)
                    except (ValueError, UnicodeError) as err:
                        raise ProtocolError("invalid_json") from err
                    return parse_response(data, now(), self.contract)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TransportError("connection_failed") from err
