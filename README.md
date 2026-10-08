# HEMS Client for Home Assistant
<img width="1448" height="1086" alt="image" src="https://github.com/user-attachments/assets/67c6c3a7-12d2-45aa-9c0e-488cfe02f8c4" />

A community Home Assistant integration for the HEMS service at [PowerGravio](https://powergravio.se). It validates local energy measurements, exchanges them with HEMS and exposes the returned decision and execution status in Home Assistant.

**0.1.0a7 is an experimental alpha.** It collects measurements, receives decisions and exposes their status. Battery control requires user-supplied HA scripts that implement and independently verify the device commands. This is not an official PowerGravio or Home Assistant integration.

HEMS Client contains no inverter driver, Modbus implementation or device-specific fallback policy. A Fronius, GEN24 or other-brand script is a separate local adapter example, not a capability supplied by this integration.

[Svenska](docs/INSTALL_SV.md) · [Adapter contract](docs/ADAPTER.md) · [Fronius GEN24 reference](docs/FRONIUS_GEN24_REFERENCE.md) · [Lessons learned](docs/LESSONS_LEARNED.md) · [Protocol](docs/PROTOCOL.md) · [Roadmap](docs/ROADMAP.md)

## What it does

- Configures the provider HTTPS address, API key and measurement entities in the HA UI.
- Accepts a provider base address and uses `/battery` automatically; a supplied endpoint path is preserved.
- Sends validated battery, grid and PV observations to HEMS and displays its decision.
- Calls an opt-in local adapter script for supported battery commands, with independent hardware readback.
- Exposes control, decision, execution and connection entities for dashboards and local automations.


## Install through HACS

Requires Home Assistant 2025.3 or later. The configuration UI was manually checked in the earlier 0.1.0a3 alpha on HA 2026.9.3 with the test entry left disabled; the screenshots are retained as a UI reference. Live cloud exchanges, hardware control and broader version compatibility still require validation. Automated tests exercise the protocol and orchestration with fake HA services.

1. In HACS, add `https://github.com/friskens/ha-hems` as a **custom repository**, category **Integration**.
2. Enable prereleases if needed and download HEMS Client.
3. Restart Home Assistant, then add **HEMS Client** under Settings → Devices & services.
4. Enter the provider's HTTPS base address or complete endpoint and your API key. A base address automatically uses `/battery`; an explicit path is kept. Select fresh measurement sensors.
5. Check the reported decisions and measurements in observation mode before configuring control scripts in the integration options.

This repository is not in the HACS default catalogue. 

Manual installation: copy `custom_components/hems` to `/config/custom_components/hems`, then restart HA.

### Measurement conventions

| Input | Meaning | Units |
| --- | --- | --- |
| Grid power | Positive import, negative export | W or kW |
| Battery power | Positive charging, negative discharging | W or kW |
| Solar power | Total PV production, including PV sent directly to the battery; multiple entities are summed | W or kW |
| Battery SOC | Current measured state of charge | % |
| EV SOC / power | Optional telemetry; does not enable charger control | % / W or kW |

Invert grid/battery signs in options when needed. Select non-overlapping PV entities: do not add an inverter total and its component channels together. Verify signs using a known charging/import/export situation. An AC-only PV sensor omits direct battery charging.

Required observations expire after 120 seconds. EV SOC has no client-side age limit: its source integration must keep it current and mark unusable readings unavailable. Repeatedly republishing a cached sensor value must not be mistaken for a fresh device measurement: see [protocol and freshness](docs/PROTOCOL.md).

## Control and adapter status

The control switch is **off by default**. With no adapter configured, the integration only sends telemetry and displays decisions. With an adapter configured, a fresh supported HEMS decision is passed to that adapter as the desired state.

Invalid measurements, responses or communication are shown as observation errors. A failed adapter write/readback is shown as an adapter or verification failure together with receipt metadata. The client keeps the HEMS decision visible as the desired state and does **not** issue a generic hardware fallback or retry command. Turning the switch off stops further client commands; local device policy, including any Auto fallback, belongs to the adapter.

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
