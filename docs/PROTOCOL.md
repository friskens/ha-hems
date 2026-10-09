# Protocol and measurement contract

This implementation follows the HEMS contract supplied during development. It is not a universal energy-management protocol; confirm compatibility with your provider.

## Request

HTTPS POST to the configured endpoint, with certificate validation and redirects disabled. Authentication: `X-Api-Key`. JSON contains numeric `soc` (%), `grid_power`, `solar_power`, `battery_power` (all W), optional `ev_power_w` and `ev_soc_pct`, `heartbeat: false`, and `app_version`. The service also accepts an optional `ev_power_by_uid` object (`{"<uid>": watts}`, nonnegative W per charger `uid`) for installations with more than one charger; this alpha does not send it.

The service also accepts an optional `load_power_w` object in the same request: `{"<load id>": watts}`, keyed by the `id` of a `loads[]` entry with `kind: "deferrable"`. Values are nonnegative W in the range 0–50 000, at most 10 entries. `0` is a real measurement (the load draws nothing); omit the key or send `null` when no measurement is available. A list or a scalar instead of an object, a negative value, a value above 50 000, more than 10 entries or a non-numeric value rejects the whole request with status 422, including the battery telemetry in it. Keys that do not match one of the account's loads are ignored. The value is used only for loads whose entry carries `reports_power: true`, and only for the exchange it arrives in: the service does not carry a load measurement over to the next exchange. Charger power is never sent here; it belongs in `ev_power_w` or `ev_power_by_uid`. This alpha does not send `load_power_w`.

No key is sent in the body. Missing measurements are not fabricated as zero. If required data is stale, the client stops submitting measurements and reports the local observation error. Optional stale EV fields are omitted.

The client sends only validated measurements and does not use `heartbeat: true`. Measurement freshness is checked locally before submission.

## Cadence

The client checks HA's existing state cache every five seconds; it does not poll inverter registers. Healthy telemetry exchanges are scheduled every 20 seconds, additionally at quarter-hour boundaries. Measurement changes of at least 200 W or 1 percentage point SOC also qualify, with a 20-second minimum spacing; quarter boundaries bypass it. Failed exchanges back off for 60 seconds, so failure backoff can postpone a quarter-boundary request. `command_interval_seconds` is validated and exposed as response metadata; it does not change the telemetry interval.

A received effective command is passed once to the configured adapter after validation. Repeated commands refresh communication without rewriting device settings. Adapter retries, hardware fallback and device policy are outside this protocol. The cadence above describes this client's current implementation, not a requirement for how the service schedules decisions.

Connection display: successful exchange age under 150 s = connected, 150–600 s = warning, 600 s or more = disconnected. These are local exchange ages, not a query of backend connection state. Failed communication or invalid input is reported locally; it does not trigger a hardware fallback command.

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

The Decision sensor exposes `command_supported` and `supported_commands`. During active control an unsupported action reports the local error `unsupported_adapter_command` without changing hardware; it is not repeatedly attempted. Telemetry continues when measurements are valid. This is local feedback only: the request currently contains no execution acknowledgement for the service.

Each `loads[]` entry carries `id` (string, unique within the list), `kind` (`"ev"` or `"deferrable"`), `name` (string, for display), `action`, `power_kw`, `power_w` (the same value in W) and `reason` (free text for display and logs; never parse it). For `kind: "ev"` the action is `charge` or `stop`, with `current_a`, `target_pct` and the optional `uid` described below. For `kind: "deferrable"` the action is `on` or `off`; `power_kw`/`power_w` is the load's configured rated power, and `reports_power` (boolean) says whether the service uses a measured `load_power_w` value for this load. A deferrable load has no `uid`; its `id` is a 32-character hexadecimal string assigned when the load was created and is the key to use in `load_power_w`. Additional informational fields may appear in an entry and must be ignored.

The Decision sensor exposes `loads` as an ordered list of validated entries in
the same shape, field names and numeric types as `loads[]` above. A field that
the service omits is omitted from the corresponding sensor entry; unknown
response fields are ignored. Malformed informational fields (`kind`, `name`,
`reason`, `uid`, `power_w` or `reports_power`) are omitted rather than rejecting
the battery decision. This replaces the earlier ID/action mapping, so local
automations must iterate the list and select the entry they need by `id` or
`uid`. The `loads` attribute is excluded from Recorder history; it remains
available as the sensor's current attribute.
Missing/null loads mean no list was supplied; an empty list is not interpreted
as an instruction to switch everything off. No load output is actuated and
`load_power_w` is not sent.

Charger loads may carry an optional `uid`: a string that identifies the charger. It is assigned by the service, stays the same for as long as the charger exists and is never reused for another charger. `id` (for example `ev_1`) is still present and remains the charger's position. The response may also contain an optional `ev_chargers` list with one object per charger: `id`, `uid`, `name` and `phases`. Both are informational for this client: unknown response fields and unknown fields in a load are ignored.

The service can run a charger check started by the customer on the HEMS pages. It uses the ordinary exchange: while the check runs, the `loads[]` entry of that charger carries a sequence of `current_a` values, a `stop` and a `charge`, and the battery decision may change as usual. No new fields are involved. A client that actuates loads must apply a new current or a stop within 3 minutes and resume charging within 6 minutes after a restart, with telemetry at least every 60 seconds. This alpha does not actuate loads, so the check cannot pass with it.

## Freshness

Required sensor values must be numeric, use recognised units and have a `last_reported` age below 120 seconds. `unknown`/`unavailable`, nonfinite values, future timestamps and invalid SOC are rejected. The integration reads current observations, not a latch whose timestamp is renewed by reuse.

A fresh PV reading of 0 W is valid at night. An unavailable PV source is not converted to zero: verify the source integration's nighttime behavior before commissioning. Missing optional EV inputs do not stop the required telemetry. Partial required telemetry is not sent without an agreed provider contract for handling missing fields.

HA's `last_reported` says when an entity reported, not when a remote device physically sampled. Configure upstream integrations to expose truthful observations. EV SOC has no client-side timeout or timestamp selector. Its source integration owns freshness and must mark unusable values unknown/unavailable; numeric values in 0–100% are accepted regardless of age. Legacy EV timeout/timestamp options are ignored. Required battery/grid/PV measurements retain their age checks. The generic client cannot detect an upstream integration repeatedly publishing cached data as fresh.

Decisions expire after 90 seconds for new writes. A previously verified stable configuration remains in place until replaced by a local adapter or other controller. A saved decision is never replayed after restart; only desired operation is persisted.
