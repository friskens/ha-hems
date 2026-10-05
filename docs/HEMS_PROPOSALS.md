# Proposals from the HEMS service

Suggestions for HEMS Client, based on 0.1.0a4. These are proposals only — the maintainers decide
what to build. Everything here concerns the client side of the `POST /battery` exchange.

**Status:** the client and the service are in sync. Header authentication, the request fields and
the response types (`power` numeric, `power_unit` `w`/`kw`, `command_interval_seconds` integer,
`action` among the nine known values) match what the service sends.

## 1. `selfconsumption` when more inverter brands are added

In 0.1.0a4, `power_kw` for `selfconsumption` is applied as a discharge ceiling. With Fronius this
works. Other brands may not: many inverters cannot limit discharge in their self-consumption mode,
or cannot report such a limit back for verification.

Proposal:

- When adding brands, let `selfconsumption` default to the inverter's own self-consumption mode,
  and apply the ceiling only where the adapter explicitly declares support for it.
- State in the installation guide that the inverter should be set to self-consumption whenever
  HEMS is not controlling it.

## 2. An invalid load entry should not stop the battery decision

Today a single entry in `loads[]` that fails validation rejects the whole response, and the client
falls back to Auto. Since loads are not actuated in the alpha, this puts battery control at risk
for no benefit.

Proposal: validate `loads[]` per entry. Log and skip an invalid entry; still apply the battery
`action` and `power_kw`.

## 3. Before adding charger and load control (roadmap)

Rules for acting on `loads[]`:

1. **Declarative.** Every response carries the desired state of every configured load. A missed
   exchange never loses a start or a stop — the next response repairs it.
2. **Act on changes only**, per `id`: `stop→charge`, `charge→stop`, `off→on`, `on→off`. Change the
   current only when `|Δcurrent_a| ≥ 1`. Repeated identical states must not cause charger writes.
3. **`current_a` may change during an ongoing charge** while `action` stays `charge`. Treat it as
   its own event.
4. **Starting must set the current in the same step.** Chargers keep their last current setpoint
   between sessions: a charger that last ran at 16 A starts at 16 A unless the start itself sets
   the requested current.
5. **Missing or `null` `loads`** means do nothing with loads (already implemented). An `id` that
   disappears from the list means the load was removed — release it silently.
6. **Service unreachable or error:** keep the last state. An ongoing charge continues; never stop
   charging because of lost communication.
7. **Position is identity:** `ev_1` ↔ `ev_power_w[0]`, `ev_2` ↔ `ev_power_w[1]`.

Fields used for control: `id`, `kind` (`ev` / `deferrable`), `action` (`charge`/`stop` for `ev`,
`on`/`off` for `deferrable`), `current_a` (whole amperes, `ev` only), `target_pct` (`ev` only).
`reason` is free text for display and logs — never parse it.

## 4. Charger current control and the charger check

The service already sends the desired charger state in every response: each `loads[]` entry with
`kind: "ev"` carries `action` (`charge` / `stop`) and `current_a` (whole amperes). The rules in
section 3 apply unchanged. Two things are needed for a Home Assistant installation to take part:

**Telemetry.** Report the charger's measured power in `ev_power_w` (W, fresh). With more than one
charger, send `ev_power_by_uid`: an object `{ "<uid>": watts }` keyed by the `uid` of each charger
(the same `uid` as in `loads[]` and `ev_chargers`). The service accepts this optional request
field today; a value in the object takes precedence over the positional `ev_power_w` list.

**The charger check.** From the HEMS pages a customer can run a check of a charger. It uses the
ordinary exchange only: for the duration of the check, the `loads[]` entry of that charger carries
a sequence of currents, a stop and a restart, and the battery decision may change as usual. The
client acts on these exactly as on any other response. For the check to pass, the installation
must:

1. Apply a new `current_a` or a `stop` within 3 minutes.
2. Resume charging within 6 minutes after a `charge` that follows a `stop`, at the requested
   current (the start itself must set the current, see section 3 rule 4).
3. Keep telemetry flowing at least every 60 seconds; a gap longer than 3 minutes aborts the check.

The result is shown on the customer's HEMS page. The response carries no check status today.

---

When a change on the service side affects the client, a pull request against `docs/PROTOCOL.md`
with a version increase will follow.
