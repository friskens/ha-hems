# HEMS Client for Home Assistant

A community Home Assistant integration for the HEMS service at [PowerGravio](https://powergravio.se), with configurable sensors and an explicit device adapter contract.

**0.1.0a2 is an experimental alpha.** It collects measurements, receives decisions and exposes their status. Battery control requires user-supplied HA scripts that implement and independently verify the device commands. A ready-made Fronius driver and automatic EV/deferrable-load control are **not included** yet. This is not an official PowerGravio, Fronius or Home Assistant integration.

[Svenska](docs/INSTALL_SV.md) · [Adapter contract](docs/ADAPTER.md) · [Lessons learned](docs/LESSONS_LEARNED.md) · [Protocol](docs/PROTOCOL.md) · [Roadmap](docs/ROADMAP.md)

## What it does

- Configure the HTTPS endpoint, API key and measurement entities in the HA UI.
- Authenticate using `X-Api-Key`; never put the key in the request body or URL.
- Send fresh SOC, grid, PV and battery power, with optional EV power and EV SOC independently of charger control.
- The current client uses `max(20, min(110, command_interval_seconds))`, measurement changes and quarter-hour boundaries to schedule telemetry. Received commands are handled independently of that cadence.
- Use unsigned `power_kw` for control; ignore the sign of the presentation field `power`.
- Avoid repeated device writes/readbacks for unchanged effective commands.
- Preserve requested operation across restart and temporary faults. Verify Auto, then require a fresh sequence before resuming; a manual stop remains stopped.
- Leave locally configured battery SOC limits untouched.

## Install through HACS

Requires Home Assistant 2025.3 or later. Runtime compatibility still needs validation on a real HA installation; the automated tests exercise the protocol and orchestration with fake HA services.

1. In HACS, add `https://github.com/friskens/ha-hems` as a **custom repository**, category **Integration**.
2. Enable prereleases if needed and download HEMS Client.
3. Restart Home Assistant, then add **HEMS Client** under Settings → Devices & services.
4. Enter the full HTTPS endpoint supplied by your HEMS provider and your API key. Select fresh measurement sensors.
5. Check the reported decisions and measurements in observation mode before configuring control scripts in the integration options.

This repository is not in the HACS default catalogue. Manual installation: copy `custom_components/hems` to `/config/custom_components/hems`, then restart HA.

### Measurement conventions

| Input | Meaning | Units |
| --- | --- | --- |
| Grid power | Positive import, negative export | W or kW |
| Battery power | Positive charging, negative discharging | W or kW |
| Solar power | Total PV production, including PV sent directly to the battery; multiple entities are summed | W or kW |
| Battery SOC | Current measured state of charge | % |
| EV SOC / power | Optional telemetry; does not enable charger control | % / W or kW |

Invert grid/battery signs in options when needed. Select non-overlapping PV entities: do not add an inverter total and its component channels together. Verify signs using a known charging/import/export situation. An AC-only PV sensor omits direct battery charging.

Required observations expire after 120 seconds. Optional EV SOC has a configurable age limit and can use a source timestamp sensor. Repeatedly republishing a cached sensor value must not be mistaken for a fresh device measurement: see [protocol and freshness](docs/PROTOCOL.md).

## Control and recovery

The control switch is **off by default**. With no adapter configured, the integration only sends telemetry and displays decisions. Starting control first calls the Auto script and verifies its receipt. It then waits for at least three successful exchanges spanning at least 60 seconds before applying a fresh supported decision.

Invalid required measurements or responses, authentication failure, and a 180-second communication outage initiate Auto recovery. A failed write/readback adds a five-minute retry delay. Auto restoration retries every 60 seconds until confirmed. These faults do not silently disable the user's requested operation. Turning the switch off cancels control and restores Auto when this integration owns the settings.

All hardware control depends on the configured scripts and their independent readback. `settings_verified` means settings were acknowledged through that contract, **not** that physical power exactly equals a target. Hardware limits remain the inverter/BMS's responsibility. Do not run two independent battery controllers at once.

## Development

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check custom_components tests
```

Tests cover protocol validation, authentication placement, measurement age/sign/unit conversion, command deduplication, restart intent and fault recovery. They do not replace testing of HA setup/config flows or live inverter behavior. Contributions should include a regression for the failure being fixed. See [CONTRIBUTING](CONTRIBUTING.md).

MIT licensed. Existing production YAML/scripts are not modified by installing this package.

## Languages and maintenance

The integration UI supports English and Swedish: configuration, entity names, modes, status and errors. Home Assistant selects translations from the user's language settings. Both languages are checked for matching keys in CI.

Open ha-hems.code-workspace for the dedicated development workspace.
