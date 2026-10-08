"""Independent telemetry and serialized adapter calls without hardware policy."""

import asyncio
from datetime import timedelta
import time
import uuid

from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .adapter import ScriptAdapter, VerificationError
from .const import DEFAULT_INTERVAL, DOMAIN, REQUIRED_FIELDS
from .measurements import Observation, collect
from .protocol import ProtocolError, due
from .recovery import Recovery
from .transport import AuthError, Client, TransportError


class Runtime:
    def __init__(self, hass, entry, session):
        self.hass, self.entry = hass, entry
        self.options = entry.options
        self.client = Client(session, entry.data["endpoint"], entry.data["api_key"])
        self.adapter = ScriptAdapter(hass, self.options.get("apply_script"), self.options.get("commands", []))
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.recovery = Recovery()
        self.decision = None
        self.status, self.error = "starting", None
        self.measurements, self.invalid = {}, []
        self.previous = {}
        self.last_attempt = self.last_success = 0
        self.last_receipt = None
        self.interval = DEFAULT_INTERVAL
        self.listeners = set()
        self._tick_task = self._write_task = None
        self._cancel_timer = None
        self._reauth_started = False
        self._closing = False
        self._exchange_failed = False

    def observe(self, entity):
        state = self.hass.states.get(entity)
        if state is None:
            return None
        return Observation(
            state.state, state.attributes.get("unit_of_measurement"), state.last_reported.timestamp()
        )

    @property
    def command_supported(self):
        if self.decision is None:
            return None
        return self.decision.action == "observe" or self.decision.action in self.adapter.commands

    def subscribe(self, callback):
        self.listeners.add(callback)
        return lambda: self.listeners.discard(callback)

    def publish(self):
        for listener in tuple(self.listeners):
            listener()

    async def save(self):
        await self.store.async_save(
            {
                "requested": self.recovery.requested,
            }
        )

    async def start(self):
        stored = await self.store.async_load() or {}
        if stored.get("requested"):
            self.recovery.request(True, time.time())
        self._cancel_timer = async_track_time_interval(self.hass, self.schedule_tick, timedelta(seconds=5))
        self.schedule_tick(None)

    @callback
    def schedule_tick(self, _):
        if not self._closing and (self._tick_task is None or self._tick_task.done()):
            self._tick_task = self.hass.async_create_task(self.tick())

    async def request(self, enabled):
        if enabled and (
            not self.adapter.apply_script or not self.adapter.commands
        ):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="adapter_required")
        self.recovery.request(enabled, time.time())
        await self.cancel_write()
        self.status = "starting" if enabled else "stopped"
        await self.save()
        self.publish()
        self.schedule_tick(None)

    async def cancel_write(self):
        if self._write_task and not self._write_task.done():
            self._write_task.cancel()
            try:
                await self._write_task
            except asyncio.CancelledError:
                pass
            # A cancelled script may have changed hardware before it stopped.
            # Its previous receipt can no longer verify the desired state.
            self.recovery.verified = None

    async def fail(self, reason):
        self.error = reason
        self.status = "observation_error"

    async def tick(self):
        now = time.time()
        if self.recovery.requested and now - self.last_success >= 180:
            await self.fail("communication_timeout")
        self.measurements, self.invalid = collect(self.options, self.observe, now)
        required_missing = any(field not in self.measurements for field in REQUIRED_FIELDS)
        if required_missing:
            await self.fail("measurements_unavailable")
        elif due(
            now, self.last_attempt, self.last_success, self.interval, self.measurements, self.previous
        ) and (not self._exchange_failed or now - self.last_attempt >= 60):
            self.last_attempt = now
            try:
                decision = await self.client.exchange(self.measurements, time.time)
            except AuthError:
                self._exchange_failed = True
                await self.fail("authentication_failed")
                if not self._reauth_started:
                    self._reauth_started = True
                    self.entry.async_start_reauth(self.hass)
            except (TransportError, ProtocolError) as err:
                self._exchange_failed = True
                self.error = str(err)
                if isinstance(err, ProtocolError) or now - self.last_success >= 180:
                    await self.fail(str(err))
            else:
                self._exchange_failed = False
                self.decision = decision
                self.last_success = decision.received_at
                self.previous = dict(self.measurements)
                if self.status == "observation_error":
                    self.error = None
                if not self.recovery.requested:
                    self.status = "observing"
                elif self.recovery.verified == decision.effective:
                    self.status = "settings_verified"
        if self.recovery.requested and self.command_supported is False:
            self.status, self.error = "adapter_failed", "unsupported_adapter_command"
        self.drive()
        self.publish()

    def drive(self):
        if self._closing or (self._write_task and not self._write_task.done()):
            return
        now = time.time()
        if self.command_supported is False:
            return
        if not self.recovery.requested or not self.decision:
            return
        if not 0 <= now - self.decision.received_at < 90:
            return
        if self.decision.action == "observe":
            # Explicitly leaves current hardware settings unchanged, as requested.
            self.status = "observing"
            self.recovery.verified = None
            return
        effective = self.decision.effective
        if self.recovery.verified != effective and self.recovery.failed != effective:
            self._write_task = self.hass.async_create_task(self.apply(self.decision, effective))

    async def apply(self, decision, effective=None):
        effective = effective or decision.effective
        self.status = "applying"
        self.publish()
        try:
            receipt = await self.adapter.execute(*effective, str(uuid.uuid4()))
        except VerificationError as err:
            self.last_receipt = err.receipt
            self.recovery.failed = effective
            self.status = (
                "adapter_failed"
                if str(err) in {"adapter_failed", "missing_adapter_script", "unsupported_adapter_command"}
                else "verification_failed"
            )
            self.error = str(err)
        else:
            self.recovery.verified = effective
            self.recovery.failed = None
            self.last_receipt = receipt
            self.status, self.error = "settings_verified", None
        await self.save()
        self.publish()

    async def stop(self):
        self._closing = True
        if self._cancel_timer:
            self._cancel_timer()
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        await self.cancel_write()
