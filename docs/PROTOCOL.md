# Protocol and measurement contract

This implementation follows the HEMS contract supplied during development. It is not a universal energy-management protocol; confirm compatibility with your provider.

## Request

HTTPS POST to the configured endpoint, with certificate validation and redirects disabled. Authentication: `X-Api-Key`. JSON contains numeric `soc` (%), `grid_power`, `solar_power`, `battery_power` (all W), optional `ev_power_w` and `ev_soc_pct`, `heartbeat: false`, and `app_version`.

No key is sent in the body. Missing measurements are not fabricated as zero. If required data is stale, the client stops submitting measurements and enters local recovery. Optional stale EV fields are omitted.

The client sends only validated measurements and does not use `heartbeat: true`. Measurement freshness is checked locally before submission.

## Cadence

The client checks HA's existing state cache every five seconds; it does not poll inverter registers. Healthy telemetry exchanges are scheduled every 20 seconds, additionally at quarter-hour boundaries. Measurement changes of at least 200 W or 1 percentage point SOC also qualify, with a 20-second minimum spacing; quarter boundaries bypass it. Failed exchanges back off for 60 seconds, so failure backoff can postpone a quarter-boundary request. `command_interval_seconds` is validated and exposed as response metadata; it does not change the telemetry interval.

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

`power_kw` is finite, numeric and nonnegative, required for charge/chargesolar/export/peakshaving/selfconsumption. For non-target actions it may be omitted and defaults to zero. `power` is presentation only and may have a user-selected sign. Accepted units are lowercase `w` or `kw`. Boolean values are not numeric. An optional `soc` response is validated but is never written as a battery limit.

Known actions: charge, chargesolar, selfconsumption, sellsolar, pause, export, peakshaving, zeroexport, observe. Unknown actions, including `unchanged`, are rejected. The adapter capability list is separate from this protocol list.

For selfconsumption, `power_kw` is the maximum battery discharge contribution, not a forced output. The client passes the action and ceiling unchanged to the adapter (converted to W), independently of EV telemetry. An explicit zero blocks discharge; an omitted ceiling is rejected. Device-specific execution belongs in adapter scripts.

The Decision sensor exposes `command_supported` and `supported_commands`. During active control an unsupported action causes verified Auto recovery and the local error `unsupported_adapter_command`; it is not repeatedly attempted. Telemetry continues when measurements are valid. This is local feedback only: the request currently contains no execution acknowledgement for the service.

Loads are validated and shown as ID/action pairs only in this alpha. Missing/null loads mean no list was supplied; an empty list is not interpreted as an instruction to switch everything off. No load output is actuated. Numerical optional fields are validated, but their values are not yet exposed for load control.

Charger loads may carry an optional `uid`: a string that identifies the charger. It is assigned by the service, stays the same for as long as the charger exists and is never reused for another charger. `id` (for example `ev_1`) is still present and remains the charger's position. The response may also contain an optional `ev_chargers` list with one object per charger: `id`, `uid`, `name` and `phases`. Both are informational for this client: unknown response fields and unknown fields in a load are ignored.

## Freshness

Required sensor values must be numeric, use recognised units and have a `last_reported` age below 120 seconds. `unknown`/`unavailable`, nonfinite values, future timestamps and invalid SOC are rejected. The integration reads current observations, not a latch whose timestamp is renewed by reuse.

A fresh PV reading of 0 W is valid at night. An unavailable PV source is not converted to zero: verify the source integration's nighttime behavior before commissioning. Missing optional EV inputs do not stop the required telemetry. Partial required telemetry is not sent without an agreed provider contract for handling missing fields.

HA's `last_reported` says when an entity reported, not when a remote device physically sampled. Configure upstream integrations to expose truthful observations. EV SOC has no client-side timeout or timestamp selector. Its source integration owns freshness and must mark unusable values unknown/unavailable; numeric values in 0–100% are accepted regardless of age. Legacy EV timeout/timestamp options are ignored. Required battery/grid/PV measurements retain their age checks. The generic client cannot detect an upstream integration repeatedly publishing cached data as fresh.

Decisions expire after 90 seconds for new writes. A previously verified stable configuration remains in place until replaced or fallback is required. A saved decision is never replayed after restart; only desired operation is persisted.
