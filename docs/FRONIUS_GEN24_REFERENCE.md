# Fronius GEN24 reference adapter

This is a reference shape from one local Home Assistant installation. It is not
bundled HEMS Client code, a generic Modbus configuration or a promise that it
fits another Fronius model, firmware, battery or installation. Configure and
independently verify every entity, register, API permission, scale and safety
limit at the site where it is used.

## Boundary

`HEMS Client` calls one local apply-and-verify script with `command`, `power_w`
and `token`. That script owns the Fronius write order and readback. A separate
local Auto script may exist for the site's manual-stop or device-failure policy,
but HEMS Client never calls it as a generic recovery action.

The local implementation has these layers:

1. `hems_hacs_apply` accepts the HEMS decision and returns the receipt.
2. `hems_write_fronius_sequence` performs this site's ordered Fronius writes.
3. `hems_fronius_verify.verify_hems_settings` performs independent readback.
4. `hems_return_auto` is an explicit local policy, not HEMS Client runtime.

## Apply-script example

This is the public shape of the top-level script. It is deliberately not a
copy-paste controller: the two called leaf scripts must be implemented and
verified for the particular installation. Replace neither placeholder with
`script.turn_on`; direct script actions are required so that Home Assistant
waits for completion and returns the verification response.

```yaml
hems_hacs_apply:
  alias: HEMS Client — apply and verify (example)
  mode: single
  fields:
    command:
      required: true
    power_w:
      required: true
    token:
      required: true
  sequence:
    - variables:
        allowed_commands:
          - charge
          - chargesolar
          - selfconsumption
          - sellsolar
          - pause
          - export
          - zeroexport

    - if:
        - condition: template
          value_template: >-
            {{ command not in allowed_commands or power_w | float(-1) < 0 }}
      then:
        - stop: "Unsupported command or negative power"
          error: true

    # Site-specific write order and device command mapping live here.
    - action: script.hems_write_device_sequence
      data:
        command: "{{ command }}"
        power_w: "{{ power_w | int }}"

    # This script must read the device independently and return a mapping such
    # as {verified: true, readback: {mode: ..., target: ...}}.
    - action: script.hems_verify_device_settings
      data:
        command: "{{ command }}"
        power_w: "{{ power_w | int }}"
      response_variable: verification

    - if:
        - condition: template
          value_template: "{{ verification.verified | default(false) }}"
      then:
        - variables:
            receipt:
              verified: true
              token: "{{ token }}"
              command: "{{ command }}"
              power_w: "{{ power_w | int }}"
              readback_at: "{{ as_timestamp(now()) }}"
              readback: "{{ verification.readback }}"
        - stop: "Independent device readback verified the requested state"
          response_variable: receipt

    - stop: "Device readback did not verify the requested state"
      error: true
```

The shown `hems_write_device_sequence` and `hems_verify_device_settings` are
intentional placeholders. Give them site-specific names if useful, but keep the
same inputs and return shape. A local failure policy may call a separate
`hems_return_auto` script after reporting the failed original command; the
apply script must not report that fallback as successful verification.

## Optional local fallback automation

HEMS Client never calls a generic fallback. If this installation should return
to a local standard state after manual stop or a decision that has been stale
for several minutes, make that choice explicit in a local automation. This
example returns to the site's `hems_return_auto` script. Replace both entity
placeholders with this HEMS Client entry's control switch and Decision sensor,
and replace the script only if the installation uses another safe default.

```yaml
automation:
  - alias: HEMS Client — local fallback after stop or stale decision (example)
    mode: single
    triggers:
      - trigger: state
        entity_id: switch.<hems_client_control>
        to: "off"
        id: manual_stop
      - trigger: template
        value_template: >-
          {% set received_at = state_attr('sensor.<hems_client_decision>', 'received_at') %}
          {{ is_state('switch.<hems_client_control>', 'on')
             and received_at is not none
             and as_timestamp(now()) - (received_at | float) > 90 }}
        for: "00:03:00"
        id: stale_decision
    actions:
      - action: script.hems_return_auto
```

The template becomes true only after the client's 90-second decision freshness
window has expired, then waits a further three minutes. `hems_return_auto` must
be idempotent and independently verify the local safe state; it must not be
configured as the HEMS Client apply script or reported as verification of the
original HEMS command. A site that should hold its current settings, retry or
choose another mode should implement that explicit policy instead.

## Mapping used by this adapter

| HEMS action | Local GEN24 interpretation |
| --- | --- |
| `charge` | Charge from grid with the requested grid-charge power |
| `chargesolar` | Block discharge with a PV charge limit |
| `selfconsumption` | Discharge Limit with the HEMS discharge ceiling |
| `sellsolar` | PV charge/discharge limit at zero |
| `pause` | Block discharge while allowing solar charge |
| `export` | Site-specific Manual/API and feed-in-target sequence |
| `zeroexport` | Zero export limit and restoration of an adapter-owned prior limit |
| `observe` | No writes |

The local script may retain a legacy internal leaf name such as `peakshaving`
when it implements the HEMS `selfconsumption` ceiling. It must not advertise
that internal name as the HEMS `peakshaving` action.

## Receipt pattern

The adapter rejects unsupported commands and negative power before writing. It
then completes its write sequence, retries its own independent readback a
bounded number of times, and returns a receipt only after the readback matches.
The public shape is:

```yaml
verified: true
token: "<unchanged HEMS Client token>"
command: "<original HEMS action>"
power_w: 2500
readback_at: 1790000000.0
readback:
  mode: "<site-verified Fronius mode>"
  target: "<site-verified target>"
```

On a local failure, the adapter may choose its own documented safety policy,
including an ordered return to Auto. It must still report a negative result for
the original HEMS decision. HEMS Client exposes that failure as
`adapter_failed` or `verification_failed`; it does not send `auto` itself.

Keep the full write sequence local. It contains installation-specific entity
names, verification-service identifiers, prior limits and device ownership
details that cannot safely be copied to another system.
