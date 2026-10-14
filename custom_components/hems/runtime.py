"""Telemetry exchange and decision presentation without equipment control."""

import asyncio
from datetime import timedelta
import time
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DEFAULT_INTERVAL, DOMAIN, REQUIRED_FIELDS
from .measurements import Observation, collect
from .protocol import ProtocolError, due
from .transport import AuthError, Client, TransportError


class Runtime:
    def __init__(self, hass, entry, session):
        self.hass, self.entry = hass, entry
        self.options = entry.options
        self.client = Client(session, entry.data["endpoint"], entry.data["api_key"])
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.telemetry_enabled = True
        self.decision = None
        self.status, self.error = "starting", None
        self.measurements, self.invalid = {}, []
        self.previous = {}
        self.last_attempt = self.last_success = 0
        self.interval = DEFAULT_INTERVAL
        self.listeners = set()
        self._tick_task = None
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

    def subscribe(self, callback):
        self.listeners.add(callback)
        return lambda: self.listeners.discard(callback)

    def publish(self):
        for listener in tuple(self.listeners):
            listener()

    async def save(self):
        await self.store.async_save(
            {
                "telemetry_enabled": self.telemetry_enabled,
            }
        )

    async def start(self):
        stored = await self.store.async_load() or {}
        # Older versions persisted ``requested`` for adapter control. It now
        # maps only to whether this client posts telemetry; it never restores
        # or changes a hardware setting.
        self.telemetry_enabled = stored.get("telemetry_enabled", stored.get("requested", True))
        self._cancel_timer = async_track_time_interval(self.hass, self.schedule_tick, timedelta(seconds=5))
        self.schedule_tick(None)

    @callback
    def schedule_tick(self, _):
        if not self._closing and (self._tick_task is None or self._tick_task.done()):
            self._tick_task = self.hass.async_create_task(self.tick())

    async def request(self, enabled):
        self.telemetry_enabled = enabled
        self.status = "starting" if enabled else "stopped"
        await self.save()
        self.publish()
        self.schedule_tick(None)

    async def fail(self, reason):
        self.error = reason
        self.status = "observation_error"

    async def tick(self):
        now = time.time()
        if self.telemetry_enabled and now - self.last_success >= 180:
            await self.fail("communication_timeout")
        self.measurements, self.invalid = collect(self.options, self.observe, now)
        required_missing = any(field not in self.measurements for field in REQUIRED_FIELDS)
        if required_missing:
            await self.fail("measurements_unavailable")
        elif self.telemetry_enabled and due(
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
                self.status = "observing"
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
