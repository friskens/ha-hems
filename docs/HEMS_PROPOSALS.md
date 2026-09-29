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

---

When a change on the service side affects the client, a pull request against `docs/PROTOCOL.md`
with a version increase will follow.
