# Lessons learned from the original HA deployment

These observations shaped this package. They are not claims that the new package has already passed live commissioning, or that every GEN24 installation behaves identically.

## Separate planning from execution

The cloud should choose a mode/target; fast self-consumption regulation belongs in the inverter. Sending a new battery power target every minute or two produced inferior self-consumption. Unrestricted self-consumption can use local Auto; a requested discharge ceiling must also be respected. Device-specific optimizations belong in adapter scripts; the generic client preserves the requested action and ceiling. See ADAPTER.md.

Telemetry cadence and actuator cadence are separate. Repeated cloud responses should not cause repeated writes or register reads. Read back after new commands, restart and recovery, and keep telemetry running while a slow actuator change is in progress.

## Preserve battery settings and power units

Do not rewrite local SOC limits merely because a cloud response includes SOC. An upper limit below current SOC can have unintended physical effects. The original installation retains its chosen 5–100% limits; those values are not universal defaults for other batteries.

Battery energy capacity in Wh is not a power base. Use verified maximum charge/discharge power/rate registers in W when translating a W target to a device percentage. A 25.6 kWh battery may separately advertise 25,600 W; the numerical coincidence does not make the units interchangeable.

An unconstrained mode should use 100% allowed where appropriate. Do not arbitrarily clamp every operation to nominal AC nameplate power: inverter/BMS current, voltage and temperature limits still apply. HEMS planning limits are separate from those physical limits.

## Fronius reference observations — not a bundled driver

- In the observed installation, a raw rate scale of -2 represented 100% as 10,000. Verify the actual model, scale factors and signed encoding before applying this elsewhere.
- Mode changes could reset limit registers. Write in the proven order and independently read back after the complete sequence.
- API mode and storage-control mode interact. The tested export path used **Target Feed In** with **Discharge to Grid**; a battery discharge slider alone did not establish the intended net export.
- Transitions between API and Modbus ownership could temporarily disrupt communication. Transition timing belongs in the adapter, not in generic HEMS protocol code.
- The original soft pause prevented discharge while allowing solar charging. `sellsolar` deliberately blocked both battery directions; a third-party driver that allowed discharge was not adopted just because it used similar hardware.
- True zero export and peak shaving need a suitable site measurement/control loop. They cannot be inferred from a battery mode label.
- A previous controller depended on a private integration client attribute. An upstream change broke verification and stranded control in Auto. This package uses a public script boundary instead, and retains requested operation through recoverable faults.

## Measurements and recovery

Always verify grid/battery sign conventions in a known physical state. Inverter RMS current can stay positive during import; it is not signed active power. Total PV should include energy charging the battery directly. Multiple inverter and EV paths make naive house-power calculations misleading.

Do not refresh the age of a cached sample when reusing it. Validate measurement freshness locally before sending data. Never send an old decision as though it were newly confirmed.

Temporary communication failure must not make the generic client choose a hardware mode. Keep desired operation separate from actual execution, show adapter verification failures clearly, and let the local adapter decide whether its hardware needs retry or Auto. A manual stop must always win.

Missing load decisions must not mean “turn everything off”. EV SOC can be useful telemetry before charger control exists. Do not copy site-specific load IDs or household entities into a generic integration.
