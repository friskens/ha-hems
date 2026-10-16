# Lessons learned from the original HA deployment

These observations shaped the HEMS Client boundary. They are not claims that
the client has been live-commissioned everywhere, or that every GEN24
installation behaves identically.

## Separate planning from execution

HEMS chooses a mode or target. Fast self-consumption regulation belongs in the
equipment or in a site's local automation. Sending a new battery-power target
every minute or two produced inferior self-consumption in the original setup.

The 0.2 client preserves that separation: it transports measurements and
presents HEMS decisions, but does not execute them. A local user-owned
automation decides which entities to write, how to avoid competing command
sequences, how to verify a result and what should happen after a local failure.

## Preserve battery settings and power units

Do not rewrite local SOC limits merely because a cloud response includes SOC.
An upper limit below current SOC can have unintended physical effects. The
original installation retained its own 5–100% limits; those are not universal
defaults for other batteries.

Battery energy capacity in Wh is not a power base. Use verified maximum
charge/discharge power or rate registers in W when translating a W target to a
device percentage. A 25.6 kWh battery may separately advertise 25,600 W; the
numerical coincidence does not make the units interchangeable.

An unconstrained mode may use 100% allowed where appropriate. Do not
arbitrarily clamp every operation to nominal AC nameplate power: inverter/BMS
current, voltage and temperature limits still apply. HEMS planning limits are
separate from those physical limits.

## Fronius reference observations — not a bundled driver

- In one observed installation, a raw rate scale of -2 represented 100% as
  10,000. Verify the actual model, scale factors and signed encoding first.
- Mode changes could reset limit registers. Write in a proven order and read
  back after the complete sequence.
- API mode and storage-control mode interact. The tested export path used
  **Target Feed In** with **Discharge to Grid**; a discharge slider alone did
  not establish the intended net export.
- API/Modbus ownership transitions could temporarily disrupt communication.
  A local automation needs its own timing and recovery policy.
- True zero export and peak shaving need a suitable site measurement/control
  loop. They cannot be inferred from a battery-mode label.

## Measurements and safety

Always verify grid/battery sign conventions in a known physical state. Inverter
RMS current can stay positive during import; it is not signed active power.
Total PV should include energy charging the battery directly. Multiple inverter
and EV paths make naïve house-power calculations misleading.

Do not refresh the age of a cached sample when reusing it. Validate measurement
freshness locally before sending data. Never present an old decision as newly
confirmed.

Temporary communication failure must not make the generic client choose a
hardware mode. The client keeps decision presentation separate from equipment
execution; the local automation owns its retry, safe-default and manual-stop
policy.

Missing load decisions do not mean “turn everything off”. EV SOC can be useful
telemetry before charger control exists. Do not copy site-specific load IDs or
household entities into a generic integration.
