"""Telemetry exchange and decision presentation without equipment control."""

import asyncio
from datetime import timedelta
import time
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DEFAULT_INTERVAL, DOMAIN
from .contract import ContractError, ContractStore, load_bundled_contract
from .measurements import MeasurementCache, Observation, collect_with_sources
from .protocol import ProtocolError, due
from .repairs import async_set_input_issues
from .telemetry_config import SelectedState, invalid_configured_inputs, known_input_keys
from .transport import AuthError, Client, TransportError


class Runtime:
    def __init__(self, hass, entry, session):
        self.hass, self.entry = hass, entry
        self.options = entry.options
        # A contract is HEMS-owned data. It declares exchange cadence and
        # accepted telemetry names, but never provides executable code.
        self.contract_store = ContractStore()
        try:
            self.contract_store = ContractStore(load_bundled_contract())
        except ContractError:
            # Surface this through normal diagnostics instead of falling back
            # to an unchecked request shape.
            pass
        self.contract = self.contract_store.current
        self.client = Client(session, entry.data["endpoint"], entry.data["api_key"], self.contract)
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.telemetry_enabled = True
        self.decision = None
        self.status, self.error = "starting", None
        self.measurements, self.invalid = {}, []
        self.measurement_cache = MeasurementCache()
        self.previous = {}
        self.last_attempt = self.last_success = 0
        self.interval = DEFAULT_INTERVAL
        self.listeners = set()
        self._tick_task = None
        self._cancel_timer = None
        self._reauth_started = False
        self._closing = False
        self._exchange_failed = False
        self._telemetry_contract = None
        self._configuration_issues: frozenset[str] | None = None
        try:
            self._telemetry_contract = load_bundled_contract()
        except ContractError:
            # A missing package resource is not silently accepted as a
            # downloaded contract.  Runtime telemetry will surface its normal
            # error; packaging validation catches this before a release.
            self._telemetry_contract = None

    def observe(self, entity):
        state = self.hass.states.get(entity)
        if state is None:
            return None
        return Observation(
            state.state, state.attributes.get("unit_of_measurement"), state.last_reported.timestamp()
        )

    def _selected_state(self, entity_id):
        """Return structural metadata only; no freshness judgement here."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        domain, _, _ = entity_id.partition(".")
        return SelectedState(
            entity_id=entity_id,
            domain=domain,
            device_class=state.attributes.get("device_class"),
            unit=state.attributes.get("unit_of_measurement"),
        )

    async def _sync_configuration_issues(self):
        """Repair only a broken saved source, never a temporarily stale one."""
        if self._telemetry_contract is None:
            return
        invalid = frozenset(
            invalid_configured_inputs(self._telemetry_contract, self.options, self._selected_state)
        )
        if invalid == self._configuration_issues:
            return
        self._configuration_issues = invalid
        await async_set_input_issues(
            self.hass,
            self.entry.entry_id,
            invalid,
            known_input_keys(self._telemetry_contract),
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
        if self.contract is None:
            await self.fail("contract_unavailable")
            self.publish()
            return
        current, self.invalid, reported = collect_with_sources(self.options, self.observe, now)
        self.measurement_cache.update(current, reported)
        await self._sync_configuration_issues()
        required_fields = tuple(
            input_.field
            for input_ in self.contract.inputs.values()
            if input_.required and input_.definition.get("client_status") != "not_sent"
        )
        stale_after = {
            input_.field: input_.stale_after_s
            for input_ in self.contract.inputs.values()
            if input_.definition.get("client_status") != "not_sent"
        }
        self.measurements = self.measurement_cache.payload(
            now,
            stale_after,
            self.invalid if self.contract.stale_on_invalid_sources else (),
        )
        # A previously valid required value remains usable (and eventually
        # appears in ``stale``).  Only a required value never observed since
        # startup prevents the exchange.
        required_missing = self.measurement_cache.missing_required(required_fields)
        if required_missing:
            await self.fail("measurements_unavailable")
        elif self.telemetry_enabled and due(
            now,
            self.last_attempt,
            self.last_success,
            self.interval,
            self.measurements,
            self.previous,
            self.contract.exchange_policy.cadence,
        ) and (
            not self._exchange_failed
            or now - self.last_attempt >= self.contract.exchange_policy.cadence.backoff_after_failure_s
        ):
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
