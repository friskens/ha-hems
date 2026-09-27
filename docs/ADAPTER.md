# Device adapter contract

This alpha calls public Home Assistant script services. It never imports another integration's private Python objects. Select an apply script, an Auto script and an explicit list of supported actions in integration options. Both scripts must return a response; use the script service directly, not `script.turn_on`.

Inputs supplied to both scripts:

| Field | Meaning |
| --- | --- |
| `command` | HEMS action, or `auto` for recovery |
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

The timeout is 120 seconds. On timeout/cancellation the client requests `script.turn_off` before recovery. Use dedicated scripts with a single execution path and no background `script.turn_on` children or detached writers; cancelling a parent cannot stop external scheduled work. Hardware or transport failure can prevent both cancellation and Auto restoration. Device-side watchdogs, where available, are still necessary.

## Action semantics

| Action | Adapter behavior |
| --- | --- |
| charge | Charge at requested target; allow solar, prevent discharge |
| chargesolar | Solar charging only, prevent discharge; interpret target explicitly |
| selfconsumption | Restore autonomous local self-consumption, without a slow outer power loop |
| pause | Soft pause: prevent discharge, allow surplus solar charging |
| sellsolar | Prefer exporting PV; prevent battery charge and discharge in this project's mapping |
| export | Controlled net grid export; target is not automatically battery discharge power |
| peakshaving | Requires a device-specific local grid-limit control loop; do not advertise unless implemented |
| zeroexport | Requires actual site export limiting; blocking the battery alone is insufficient |
| observe | The runtime sends no actuator command and leaves existing settings unchanged |
| auto | Clear controls owned by this adapter and restore local autonomous behavior |

`selfconsumption`, `pause`, `sellsolar` and `zeroexport` ignore changing response watts for deduplication. Supported actions must match these semantics; do not tick every action merely because its name is recognised.

No SOC min/max is passed to scripts. Do not add unsolicited SOC writes. Do not silently convert an unsupported action into a different action: signal a failure and let Auto recovery handle it.

## Recovery sequence

1. Persist desired operation and ownership before a write.
2. On a fault, stop the active script and request verified Auto. Repeated invalid samples do not repeatedly cancel this restoration.
3. Retry unconfirmed Auto every 60 seconds, retaining desired operation.
4. Require three successful exchanges spanning at least 60 seconds, a decision younger than 90 seconds, and no gaps of 120 seconds or more in the good sequence.
5. After a write/verification fault also wait at least 300 seconds, then retry the latest fresh decision.

Manual stop clears desired operation and restores Auto if settings were owned. Restart with desired operation enabled always re-enters recovery rather than replaying an old command. The control switch remains on during recovery because it represents intent; the Execution sensor shows actual progress.
