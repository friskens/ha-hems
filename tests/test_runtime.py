"""Orchestration regressions with fake HA storage/services, not hardware tests."""

import asyncio
import importlib
import sys
import types
from unittest.mock import ANY, AsyncMock

import pytest

from custom_components.hems.protocol import Decision


@pytest.fixture
def runtime(monkeypatch):
    for name in (
        "homeassistant",
        "homeassistant.helpers",
        "homeassistant.core",
        "homeassistant.exceptions",
        "homeassistant.helpers.event",
        "homeassistant.helpers.storage",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["homeassistant.exceptions"].HomeAssistantError = RuntimeError
    sys.modules["homeassistant.core"].callback = lambda function: function
    sys.modules["homeassistant.helpers.event"].async_track_time_interval = lambda *args: lambda: None
    sys.modules["homeassistant.helpers.storage"].Store = lambda *args: types.SimpleNamespace(
        async_save=AsyncMock(), async_load=AsyncMock(return_value={})
    )
    sys.modules.pop("custom_components.hems.runtime", None)
    module = importlib.import_module("custom_components.hems.runtime")
    monkeypatch.setattr(module.time, "time", lambda: 1000)
    hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
    entry = types.SimpleNamespace(
        options={}, data={"endpoint": "https://example.com/battery", "api_key": "test"}, entry_id="test"
    )
    result = module.Runtime(hass, entry, None)
    result.adapter.commands = {"selfconsumption", "pause", "export"}
    result.adapter.execute = AsyncMock()
    return result


async def test_observation_failure_never_writes_auto(runtime):
    runtime.recovery.requested = True
    runtime.decision = Decision("pause", 0, 1000)
    await runtime.fail("stale")
    assert runtime.status == "observation_error"
    runtime.adapter.execute.assert_not_awaited()


async def test_identical_decision_does_not_write_again(runtime):
    runtime.recovery.requested = True
    runtime.measurements = {"ev_power_w": 0}
    runtime.decision = Decision("selfconsumption", 1, 1000)
    runtime.drive()
    await runtime._write_task
    runtime.decision = Decision("selfconsumption", 1, 1000)
    runtime.drive()
    assert runtime.adapter.execute.await_count == 1


async def test_ev_changes_do_not_remap_action_but_cap_changes_trigger_writes(runtime):
    runtime.recovery.requested = True
    runtime.decision = Decision("selfconsumption", 2, 1000)
    for ev, cap, expected in [
        (0, 2, ("selfconsumption", 2000)),
        (7000, 2, ("selfconsumption", 2000)),
        (7000, 1, ("selfconsumption", 1000)),
        (0, 1, ("selfconsumption", 1000)),
        (None, 1, ("selfconsumption", 1000)),
    ]:
        runtime.measurements = {"ev_power_w": ev}
        runtime.decision = Decision("selfconsumption", cap, 1000)
        runtime.drive()
        await runtime._write_task
        assert runtime.adapter.execute.call_args.args[:2] == expected
    assert runtime.adapter.execute.await_count == 2


async def test_write_failure_preserves_pause_without_auto_fallback(runtime):
    from custom_components.hems.adapter import VerificationError

    runtime.recovery.requested = True
    decision = Decision("pause", 0, 1000)
    runtime.decision = decision
    runtime.adapter.execute.side_effect = VerificationError("verification_failed")
    await runtime.apply(decision)
    assert runtime.recovery.requested
    assert runtime.decision == decision
    assert runtime.recovery.failed == decision.effective
    assert runtime.status == "verification_failed"
    runtime.adapter.execute.assert_awaited_once_with("pause", 0, ANY)
    runtime.drive()
    runtime.adapter.execute.assert_awaited_once()


async def test_manual_stop_wins(runtime):
    runtime.recovery.requested = True
    runtime.schedule_tick = lambda _: None
    await runtime.request(False)
    assert not runtime.recovery.requested
    runtime.adapter.execute.assert_not_awaited()
    assert runtime.status == "stopped"


async def test_observer_never_writes(runtime):
    runtime.decision = Decision("export", 11, 1000)
    runtime.drive()
    assert runtime._write_task is None


async def test_restart_keeps_desired_run_without_hardware_fallback(runtime):
    runtime.store.async_load.return_value = {"requested": True}
    runtime.schedule_tick = lambda _: None
    await runtime.start()
    assert runtime.recovery.requested
    runtime.adapter.execute.assert_not_awaited()


async def test_telemetry_continues_while_actuator_waits(runtime, monkeypatch):
    module = sys.modules["custom_components.hems.runtime"]
    sample = {"soc": 50, "grid_power": 500, "solar_power": 1000, "battery_power": 500}
    monkeypatch.setattr(module, "collect", lambda *args: (sample, []))
    runtime.client.exchange = AsyncMock(return_value=Decision("pause", 0, 1000))
    runtime._write_task = asyncio.create_task(asyncio.Event().wait())
    await runtime.tick()
    runtime.client.exchange.assert_awaited_once()
    assert not runtime._write_task.done()
    await runtime.cancel_write()


async def test_command_interval_does_not_delay_telemetry(runtime, monkeypatch):
    module = sys.modules["custom_components.hems.runtime"]
    sample = {"soc": 50, "grid_power": 0, "solar_power": 0, "battery_power": 0}
    monkeypatch.setattr(module, "collect", lambda *args: (sample, []))
    runtime.client.exchange = AsyncMock(return_value=Decision("pause", 0, 1000, 300))
    await runtime.tick()
    monkeypatch.setattr(module.time, "time", lambda: 1020)
    await runtime.tick()
    assert runtime.client.exchange.await_count == 2
    assert runtime.interval == 20
    assert runtime.decision.interval == 300


async def test_unsupported_command_remains_visible_without_auto_fallback(runtime, monkeypatch):
    module = sys.modules["custom_components.hems.runtime"]
    sample = {"soc": 50, "grid_power": 0, "solar_power": 0, "battery_power": 0}
    monkeypatch.setattr(module, "collect", lambda *args: (sample, []))
    runtime.client.exchange = AsyncMock(return_value=Decision("zeroexport", 0, 1000))
    runtime.recovery.requested = True
    runtime.last_success = 990
    await runtime.tick()
    for stamp in (1020, 1040, 1060, 1080):
        monkeypatch.setattr(module.time, "time", lambda: stamp)
        await runtime.tick()
    assert runtime.command_supported is False
    assert runtime.error == "unsupported_adapter_command"
    assert runtime.status == "adapter_failed"
    assert runtime.recovery.requested
    runtime.adapter.execute.assert_not_awaited()
    assert runtime.client.exchange.await_count == 5


async def test_failed_exchange_backs_off_then_resumes_twenty_second_cadence(runtime, monkeypatch):
    from custom_components.hems.transport import TransportError

    module = sys.modules["custom_components.hems.runtime"]
    sample = {"soc": 50, "grid_power": 0, "solar_power": 0, "battery_power": 0}
    monkeypatch.setattr(module, "collect", lambda *args: (sample, []))
    runtime.client.exchange = AsyncMock(side_effect=[
        TransportError("offline"), Decision("pause", 0, 1060), Decision("pause", 0, 1080),
    ])
    await runtime.tick()
    for stamp in (1020, 1040):
        monkeypatch.setattr(module.time, "time", lambda: stamp)
        await runtime.tick()
    assert runtime.client.exchange.await_count == 1
    for stamp in (1060, 1080):
        monkeypatch.setattr(module.time, "time", lambda: stamp)
        await runtime.tick()
    assert runtime.client.exchange.await_count == 3


@pytest.mark.parametrize("missing", [False, True])
async def test_nighttime_zero_is_valid_but_missing_pv_blocks(runtime, monkeypatch, missing):
    module = sys.modules["custom_components.hems.runtime"]
    sample = {"soc": 50, "grid_power": 500, "battery_power": 0}
    if not missing:
        sample["solar_power"] = 0
    monkeypatch.setattr(module, "collect", lambda *args: (sample, ["solar_power"] if missing else []))
    runtime.client.exchange = AsyncMock(return_value=Decision("pause", 0, 1000))
    await runtime.tick()
    assert runtime.client.exchange.await_count == (0 if missing else 1)
