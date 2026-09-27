# Protocol and measurement contract

This implementation follows the HEMS contract supplied during development. It is not a universal energy-management protocol; confirm compatibility with your provider.

## Request

HTTPS POST to the configured endpoint, with certificate validation and redirects disabled. Authentication: `X-Api-Key`. JSON contains numeric `soc` (%), `grid_power`, `solar_power`, `battery_power` (all W), optional `ev_power_w` and `ev_soc_pct`, `heartbeat: false`, and `app_version`.

No key is sent in the body. Missing measurements are not fabricated as zero. If required data is stale, the client stops submitting measurements and enters local recovery. Optional stale EV fields are omitted.

The client sends only validated measurements and does not use `heartbeat: true`. Measurement freshness is checked locally before submission.

## Cadence

The client checks HA's existing state cache every five seconds; it does not poll inverter registers. Requests follow `max(20, min(110, command_interval_seconds))`, additionally at quarter-hour boundaries and on changes of at least 200 W or 1 percentage point SOC. Change-triggered requests have a 20-second minimum spacing; quarter boundaries bypass it. Failed exchanges back off for 60 seconds, so failure backoff can postpone a quarter-boundary request.

A received effective command is applied once it passes validation and recovery gates. Repeated commands refresh communication without rewriting device settings. The cadence above describes this client's current implementation, not a requirement for how the service schedules decisions.

Connection display: successful exchange age under 150 s = connected, 150–600 s = warning, 600 s or more = disconnected. These are local exchange ages, not a query of backend connection state. Local control fallback begins at 180 seconds of failed communication or immediately for invalid required input/response.

## Response

```json
{
  "action": "export",
  "power_kw": 2.5,
  "power": -2500,
  "power_unit": "w",
  "command_interval_seconds": 110,
  "loads": []
}
```

`power_kw` is finite, numeric and nonnegative, required for charge/chargesolar/export/peakshaving. For non-target actions it may be omitted and defaults to zero. `power` is presentation only and may have a user-selected sign. Accepted units are lowercase `w` or `kw`. Boolean values are not numeric. An optional `soc` response is validated but is never written as a battery limit.

Known actions: charge, chargesolar, selfconsumption, sellsolar, pause, export, peakshaving, zeroexport, observe. Unknown actions, including `unchanged`, are rejected. The adapter capability list is separate from this protocol list.

Loads are validated and shown as ID/action pairs only in this alpha. Missing/null loads mean no list was supplied; an empty list is not interpreted as an instruction to switch everything off. No load output is actuated. Numerical optional fields are validated, but their values are not yet exposed for load control.

## Freshness

Required sensor values must be numeric, use recognised units and have a `last_reported` age below 120 seconds. `unknown`/`unavailable`, nonfinite values, future timestamps and invalid SOC are rejected. The integration reads current observations, not a latch whose timestamp is renewed by reuse.

HA's `last_reported` says when an entity reported, not when a remote device physically sampled. Configure upstream integrations to expose truthful observations. EV SOC has no client-side timeout or timestamp selector. Its source integration owns freshness and must mark unusable values unknown/unavailable; numeric values in 0–100% are accepted regardless of age. Legacy EV timeout/timestamp options are ignored. Required battery/grid/PV measurements retain their age checks. The generic client cannot detect an upstream integration repeatedly publishing cached data as fresh.

Decisions expire after 90 seconds for new writes. A previously verified stable configuration remains in place until replaced or fallback is required. A saved decision is never replayed after restart; only desired operation is persisted.
