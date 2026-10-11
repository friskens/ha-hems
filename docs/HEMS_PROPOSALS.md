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

Today a single entry in `loads[]` that fails validation rejects the whole response. A generic
hardware fallback would put battery control at risk, since loads are not actuated in the alpha,
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

## 5. Deferrable loads: on/off actuation and measured power

The service already sends the desired state of every configured deferrable load in each response:
`loads[]` entries with `kind: "deferrable"` carry `action` (`on` / `off`), the rated power
(`power_kw`, `power_w`) and `reports_power`. The rules in section 3 apply unchanged. For a Home
Assistant installation to take part, two things are needed in the client:

**Actuation.** Map each load `id` to a switch (or a script pair) in the integration options. Act
declaratively and on changes only: `off→on` turns the entity on, `on→off` turns it off, and a repeated
identical state causes no write. A load whose `id` disappears from the list is released without a
write. When the service is unreachable or returns an error, keep the last state; never switch a load
off because communication was lost. Verify the result by reading the entity state back, as the adapter
contract requires for the battery.

**Measured power.** For a load with `reports_power: true`, map a power sensor (W) to the load `id` and
send its fresh value in every exchange as `load_power_w[id]`. Apply the same freshness rules as for the
other measurements: a stale, `unknown` or `unavailable` sensor means the key is omitted for that
exchange, never sent as `0`. A fresh `0` is a valid measurement. Values are whole or decimal W,
0–50 000. The service uses the value only while it has the load switched on and shows it on the
customer's HEMS page within one exchange; a value far above the rated power is treated as a
misconnected sensor and discarded. The response carries no acknowledgement of the value; status 200
means the whole request was accepted.

## 6. Per-phase current at the main fuse

The service accepts the current on each phase at the main fuse as the optional request field
`phase_current_a` (see PROTOCOL.md). With per-phase values the service can keep each phase within
the main fuse rating, not only the total: an unbalanced load, for example a single-phase car
charger, can overload one phase while the total import stays below the limit. Without them, only
the total is known.

Proposal for the client:

1. **Options.** Three optional current sensors, L1, L2 and L3, in the measurement options. Map all
   three or none; a partial mapping is a configuration error. Missing phase sensors must not stop
   the required telemetry.
2. **Unit and sign.** Accept `A` (convert `mA` if the source uses it). Send the absolute value: some
   meters report a negative current while exporting. A negative value or a value above 250 A makes
   the service ignore the field.
3. **Freshness.** Apply the same checks as for the required measurements: `last_reported` age below
   120 seconds, no `unknown`/`unavailable`, finite numbers. If any phase fails, omit
   `phase_current_a` for that exchange. Never send `0` for a phase that is not measured, and never
   send fewer than three values.
4. **Every exchange.** Send the field with every exchange while the sensors are valid; an omitted
   field is read as unknown for that exchange.
5. **Source.** Use the per-phase current of the grid meter at the connection point, not the
   inverter's output current per phase, which does not include the house load.
6. **Request allowlist.** Add `phase_current_a` to the fixed list of request fields in the
   transport.

The response is unchanged. There is no acknowledgement of the values beyond status 200.

---

When a change on the service side affects the client, a pull request against `docs/PROTOCOL.md`
with a version increase will follow.
