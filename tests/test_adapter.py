import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.hems.adapter import ScriptAdapter, VerificationError


async def test_successful_script_receipt():
    async def call(domain, service, data, **kwargs):
        assert domain == "script" and service == "apply"
        assert kwargs == {"blocking": True, "return_response": True}
        return {**data, "verified": True, "readback_at": time.time(), "readback": {"mode": 3}}

    adapter = ScriptAdapter(
        SimpleNamespace(services=SimpleNamespace(async_call=call)), "script.apply", ["pause"]
    )
    receipt = await adapter.execute("pause", 0, "token")
    assert receipt["token"] == "token"
    assert receipt["command"] == "pause"


async def test_unsupported_action_never_calls_service():
    call = AsyncMock()
    adapter = ScriptAdapter(
        SimpleNamespace(services=SimpleNamespace(async_call=call)), "script.apply", ["pause"]
    )
    with pytest.raises(VerificationError):
        await adapter.execute("export", 1000, "token")
    call.assert_not_called()


async def test_cancel_requests_script_stop():
    entered = asyncio.Event()
    calls = []

    async def call(domain, service, data, **kwargs):
        calls.append(service)
        if service == "apply":
            entered.set()
            await asyncio.Event().wait()

    adapter = ScriptAdapter(
        SimpleNamespace(services=SimpleNamespace(async_call=call)), "script.apply", ["pause"]
    )
    task = asyncio.create_task(adapter.execute("pause", 0, "token"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["apply", "turn_off"]


async def test_service_errors_are_sanitized_even_if_stop_fails():
    call = AsyncMock(side_effect=RuntimeError("private device credential"))
    adapter = ScriptAdapter(
        SimpleNamespace(services=SimpleNamespace(async_call=call)), "script.apply", ["pause"]
    )
    with pytest.raises(VerificationError, match="^adapter_failed$"):
        await adapter.execute("pause", 0, "token")
