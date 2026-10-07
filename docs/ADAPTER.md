# Device adapter contract

This alpha calls public Home Assistant script services. It never imports another integration's private Python objects. Select an apply script and an explicit list of supported actions in integration options. The script must return a response; use the script service directly, not `script.turn_on`.

Inputs supplied to both scripts:

| Field | Meaning |
| --- | --- |
| `command` | HEMS action supplied as the desired state |
| `power_w` | Nonnegative target in W; zero for no-target modes |
| `token` | Unique request identifier; echo unchanged |

The script must perform ordered writes, then **independently read back** the hardware configuration. Return this structure using HA's `stop` action with `response_variable`:

```yaml
# Receipt shape only. This is NOT a runnable verification implementation.
verified: true
token: "<the supplied token>"
command: "<the supplied command>"
power_w: 2500
readback_at: 1790000000.0  # Actual readback Unix time, after this request began.
readback:
  mode: "<fresh hardware mode>"
  target: "<fresh hardware target>"
```

Only set `verified: true` after comparing fresh device values with the requested settings, including relevant mode and limits. A successful HA service call, optimistic entity state, echoed request or old cache is not confirmation. The client validates receipt identity and timestamp; the **script is responsible for interpreting hardware readback truthfully**.

The timeout is 120 seconds. On timeout/cancellation the client requests `script.turn_off` for the in-flight adapter script only. Use dedicated scripts with a single execution path and no background `script.turn_on` children or detached writers; cancelling a parent cannot stop external scheduled work. Hardware or transport failure can prevent cancellation. Device-side watchdogs, retries and any local Auto fallback, where needed, are adapter policy.

## Action semantics

| Action | Adapter behavior |
| --- | --- |
| charge | Charge at requested target; allow solar, prevent discharge |
| chargesolar | Solar charging only, prevent discharge; interpret target explicitly |
| selfconsumption | Autonomous local regulation with `power_w` as maximum battery discharge; zero blocks discharge |
| pause | Soft pause: prevent discharge, allow surplus solar charging |
| sellsolar | Prefer exporting PV; prevent battery charge and discharge in this project's mapping |
| export | Controlled net grid export; target is not automatically battery discharge power |
| peakshaving | Requires a device-specific local grid-limit control loop; do not advertise unless implemented |
| zeroexport | Requires actual site export limiting; blocking the battery alone is insufficient |
| observe | The runtime sends no actuator command and leaves existing settings unchanged |

`pause`, `sellsolar` and `zeroexport` ignore changing response watts for deduplication. A changed selfconsumption ceiling is a new effective command. Supported actions must match these semantics; do not tick every action merely because its name is recognised.

No SOC min/max is passed to scripts. Do not add unsolicited SOC writes. Do not silently convert an unsupported action into a different action: return a failure receipt. The generic client does not issue `auto` or any other fallback command; if an adapter needs Auto after a local failure, that is its own explicitly documented device policy.

An action outside the configured capability list is reported as `unsupported_adapter_command` during active control. The client retains the desired decision and continues valid telemetry without changing hardware. The Decision sensor exposes capability support even in observation mode. The adapter receipt is exposed locally in HA; no execution acknowledgement is sent to the HEMS service by this version because its provider contract has no such field.

### Self-consumption and EV charging

The generic client always passes `selfconsumption` and its discharge ceiling to
the adapter, regardless of EV telemetry. It does not select an inverter mode or
subtract EV power from the ceiling. Zero means zero permitted discharge; missing
`power_kw` is rejected rather than interpreted as an unlimited target.

Device-specific mode selection, percentage conversion, write ordering and local
EV-related optimizations belong in the adapter scripts. Do not assume another
inverter behaves like the original installation. An adapter with local inputs
must handle their changes and freshness itself, including between unchanged
HEMS decisions, and independently verify any resulting setting changes.

Adapters advertising selfconsumption must implement this ceiling contract.
Existing adapters that always map it to unrestricted Auto must be updated before
enabling this version. No device-specific adapter is bundled.

## Failure and ownership boundary

The client persists only whether control was requested. It never persists and replays an old hardware decision after restart. On a new, fresh HEMS decision it calls the adapter once. A verified receipt records `settings_verified`; an adapter/service failure records `adapter_failed`; an invalid or missing receipt records `verification_failed`. The desired HEMS decision remains visible in all cases.

The client does not send `auto`, retry a failed hardware write, or decide a fallback mode. Those actions require device-specific knowledge and belong in the adapter. Manual stop cancels an in-flight adapter script and prevents further client commands; it does not alter hardware settings.
