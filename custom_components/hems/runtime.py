"""Independent telemetry and serialized actuator tasks with automatic recovery."""

import asyncio
from datetime import timedelta
import time
import uuid

from homeassistant.exceptions import HomeAssistantError
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
        self.adapter = ScriptAdapter(
            hass,
            self.options.get("apply_script"),
            self.options.get("auto_script"),
            self.options.get("commands", []),
        )
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.recovery = Recovery()
        self.decision = None
        self.status, self.error = "starting", None
        self.measurements, self.invalid = {}, []
        self.previous = {}
        self.last_attempt = self.last_success = self.last_restore = 0
        self.interval = DEFAULT_INTERVAL
        self.listeners = set()
        self._tick_task = self._write_task = None
        self._cancel_timer = None
        self._owned = False
        self._reauth_started = False
        self._closing = False

    def observe(self, entity):
        state = self.hass.states.get(entity)
        if state is None:
            return None
        return Observation(
            state.state, state.attributes.get("unit_of_measurement"), state.last_reported.timestamp()
        )

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
                "restore_pending": self.recovery.restore_pending,
                "owned": self._owned,
            }
        )

    async def start(self):
        stored = await self.store.async_load() or {}
        if stored.get("requested"):
            self.recovery.request(True, time.time())
        elif stored.get("restore_pending") or stored.get("owned"):
            self.recovery.restore_pending = True
        self._owned = bool(stored.get("owned"))
        self._cancel_timer = async_track_time_interval(self.hass, self.schedule_tick, timedelta(seconds=5))
        self.schedule_tick(None)

    def schedule_tick(self, _):
        if not self._closing and (self._tick_task is None or self._tick_task.done()):
            self._tick_task = self.hass.async_create_task(self.tick())

    async def request(self, enabled):
        if enabled and (
            not self.adapter.apply_script or not self.adapter.auto_script or not self.adapter.commands
        ):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="adapter_required")
        self.recovery.request(enabled, time.time())
        # A fresh observer-only installation must never touch equipment.
        if not enabled and not self._owned:
            self.recovery.restore_pending = False
        await self.cancel_write()
        self.status = "recovering" if enabled else "stopped"
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

    async def fail(self, reason, control=False):
        self.error = reason
        self.recovery.reset_good()
        if self.recovery.requested or self._owned:
            # Enter fallback once. Repeated stale samples must not cancel Auto
            # while it is still restoring, or repeatedly rewrite verified Auto.
            if not self.recovery.pending and not self.recovery.restore_pending:
                self.recovery.fault(time.time(), control)
                await self.cancel_write()
                await self.save()
            if not self.recovery.restore_pending:
                self.status = "recovering"
        else:
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
        ) and (not self.error or now - self.last_attempt >= 60):
            self.last_attempt = now
            try:
                decision = await self.client.exchange(self.measurements, time.time)
            except AuthError:
                await self.fail("authentication_failed")
                if not self._reauth_started:
                    self._reauth_started = True
                    self.entry.async_start_reauth(self.hass)
            except (TransportError, ProtocolError) as err:
                self.recovery.reset_good()
                self.error = str(err)
                if isinstance(err, ProtocolError) or now - self.last_success >= 180:
                    await self.fail(str(err))
            else:
                self.decision = decision
                self.last_success = decision.received_at
                self.previous = dict(self.measurements)
                self.interval = decision.interval
                self.error = None
                self.recovery.good(decision.received_at)
                if not self.recovery.requested and not self.recovery.restore_pending:
                    self.status = "observing"
        self.drive()
        self.publish()

    def drive(self):
        if self._closing or (self._write_task and not self._write_task.done()):
            return
        now = time.time()
        if self.recovery.restore_pending:
            if now - self.last_restore >= 60:
                self.last_restore = now
                self._write_task = self.hass.async_create_task(self.restore())
            return
        if self.recovery.can_resume(now, self.decision):
            self.recovery.pending = False
        if not self.recovery.requested or self.recovery.pending or not self.decision:
            return
        if not 0 <= now - self.decision.received_at < 90:
            return
        if self.decision.action == "observe":
            # Explicitly leaves current hardware settings unchanged, as requested.
            self.status = "observing"
            self.recovery.verified = None
            return
        if self.recovery.verified != self.decision.effective:
            self._write_task = self.hass.async_create_task(self.apply(self.decision))

    async def restore(self):
        self.status = "restoring_auto"
        self.publish()
        try:
            await self.adapter.execute("auto", 0.0, str(uuid.uuid4()))
        except VerificationError:
            self.error, self.status = "auto_unconfirmed", "recovering"
        else:
            self.recovery.restore_pending = False
            self._owned = False
            self.status = "recovering" if self.recovery.requested else "stopped"
            self.error = None
        await self.save()
        self.publish()

    async def apply(self, decision):
        self._owned = True  # Persist before any hardware write, including partial writes.
        await self.save()
        self.status = "applying"
        self.publish()
        try:
            await self.adapter.execute(*decision.effective, str(uuid.uuid4()))
        except VerificationError:
            self.recovery.fault(time.time(), control=True)
            self.status, self.error = "recovering", "write_unconfirmed"
        else:
            self.recovery.verified = decision.effective
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
        if self._owned or self.recovery.restore_pending:
            self.recovery.restore_pending = True
            await self.save()
            await self.restore()
