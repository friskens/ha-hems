# Local automation migration

This guide is for a local Home Assistant automation that consumes HEMS Client
entities. It contains no hardware commands or vendor-specific configuration.
The authoritative fields and action meanings are in generated
[PROTOCOL.md](PROTOCOL.md).

## Removed in 0.2

HEMS Client no longer:

- calls adapter scripts or any Home Assistant service to operate equipment;
- selects an inverter, charger or other device integration;
- retries a command, verifies that equipment changed state, or restores an
  inverter mode such as `Auto` after a failure, timeout or manual stop;
- treats a missing `loads` entry as a request to turn that load off.

Remove dependencies on old adapter selection, `auto_script`, ownership or
restore state. Put the desired failure, stale-decision and manual-stop policy
in the local automation that owns the equipment.

## What the automation reads

`sensor.hems_decision` is informational. Its state is the HEMS `action`; its
declared attributes include `power_kw`, derived `power_w`,
`command_interval_seconds`, `fresh`, `loads` and `ev_chargers` when supplied.
Do not use an old decision after `fresh` is false.

The contract also declares separate presentation entities such as the decision
freshness binary sensor, power target, command interval and connection. Their
names and thresholds are contract-owned and may be extended in a later
contract. Match stable entity IDs/unique IDs rather than translated labels.

## Loads and EV charging

`loads` is an ordered list, never an `{id: action}` mapping. An empty list
means no entries; `null`/missing means that HEMS supplied no list. Neither is a
global off command.

For `kind: ev`, action is `charge` or `stop`, not `on` or `off`. If present,
read `current_a` and `target_pct` as the desired EV charging parameters.
Match a charger by its stable `uid`; use `id` for another load. The display
`name` may change.

For `kind: deferrable`, action is `on` or `off`. `enabled: false` says that the
customer has disabled the service's control of that load. `reason` is
display-only text: it is available as an attribute for dashboards, but it is
not a command or an instruction to parse.

HEMS Client may also expose one informational dynamic sensor per current load.
It keeps the HEMS identity and becomes unavailable when an entry is absent; it
does not delete the entity. The dynamic sensor exposes only the fields listed
by the contract's `attributes_from_entry`.

## Safe local automation shape

Use one automation you own, triggered by a decision update, with `mode:
restart`. First require a fresh decision, then use a `choose` branch for each
contract action. Within the EV branch, distinguish `charge` from `stop` and
apply only the optional parameters the selected local charger integration
supports. Decide locally what should happen if HEMS is unavailable or a
decision is stale; HEMS Client deliberately does not choose that fallback.
