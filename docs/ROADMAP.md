# Roadmap

## Current alpha scope

0.2.0a1 consumes the co-maintainer-owned HEMS contract, configures existing
telemetry sources from its safe declarative inputs, sends validated telemetry and
exposes decisions, freshness, connection and informational load/charger
entities. HEMS Client does not operate equipment: one user-owned Home Assistant
automation consumes each decision. EV and load data remain informational.

See [CHANGELOG](../CHANGELOG.md) for the delivered changes in each alpha rather
than treating the original a1 scope as the current implementation.

## Before recommending active use

- Test config flow, reauthentication, reload/unload and startup in real Home Assistant.
- Build and test the local automation for every action used by an installation.
- Verify decision freshness, source loss, endpoint loss and recovery without
  HEMS Client making a device write.
- Validate installation/update through HACS against the supported HA versions.
- Test telemetry schema against the intended provider deployment; no real account or credentials are included in tests.

## Follow-up features

- Optional brand-specific automation blueprints (for example Fronius) that use
  the same decision sensor without becoming part of the generic client.
- Explicit load-ID mapping and local on/off automation examples for deferrable
  loads, including daily budgets and source freshness.
- EV charger automation blueprints and richer informational diagnostics.
- Provider capability discovery: retrieve a newer contract safely, validate it,
  retain the last valid copy and ignore unsupported declarative fields.
- HA-native config-flow tests and hardware-independent end-to-end test harness.

Do not migrate an existing working controller merely to try the alpha. Stage the new client in observation mode, compare measurements/decisions, then arrange a single-writer handover.
