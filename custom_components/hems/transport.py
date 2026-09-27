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
    def __init__(self, session, url, key):
        self.session = session
        self.url = endpoint(url)
        self._key = key

    async def exchange(self, measurements, now):
        # Fixed allowlist prevents callers from reintroducing credentials in body.
        allowed = {"soc", "grid_power", "solar_power", "battery_power", "ev_power_w", "ev_soc_pct"}
        payload = {k: v for k, v in measurements.items() if k in allowed}
        payload.update(heartbeat=False, app_version=f"ha-hems/{VERSION}")
        try:
            async with asyncio.timeout(15):
                async with self.session.post(
                    self.url,
                    headers={"X-Api-Key": self._key},
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
                        if len(raw) > 65536:
                            raise ProtocolError("response_too_large")
                    try:
                        data = json.loads(raw)
                    except (ValueError, UnicodeError) as err:
                        raise ProtocolError("invalid_json") from err
                    return parse_response(data, now())
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TransportError("connection_failed") from err
