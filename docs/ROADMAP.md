# Roadmap

## Included in 0.1.0a1

Config flow, source selection/sign conversion, header authentication, bounded JSON validation, cadence, decision/status entities, optional EV telemetry, persistent control intent, script receipt contract, recovery and core regression tests.

## Before recommending active use

- Test config flow, reauthentication, reload/unload and startup in real Home Assistant.
- Commission an adapter against real equipment with independent register/API readback.
- Verify every advertised action, cancellation, source loss, endpoint loss and recovery.
- Validate installation/update through HACS against the supported HA versions.
- Test telemetry schema against the intended provider deployment; no real account or credentials are included in tests.

## Follow-up features

- Optional brand-specific reference adapters (for example Fronius) through stable supported APIs, with explicit capability/version checks, no private integration imports, and no bundled inverter driver.
- Explicit load-ID mapping and verified on/off behavior for deferrable loads, including daily budgets and source freshness.
- EV charger adapter and actual charging verification; EV SOC telemetry already works independently.
- Provider capability discovery and richer load decision diagnostics.
- HA-native config-flow tests and hardware-independent end-to-end test harness.

Do not migrate an existing working controller merely to try the alpha. Stage the new client in observation mode, compare measurements/decisions, then arrange a single-writer handover.
