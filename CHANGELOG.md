# Changelog

## Unreleased

EV SOC freshness is now owned by the source integration. Removed the EV SOC timeout and timestamp selectors, added English/Swedish guidance, and retained numeric/range validation. Existing timeout/timestamp options are ignored.

## 0.1.0a2

Swedish and English config/options, entity names, decision/execution/connection states, command selectors and user-facing adapter errors. Added HACS validation, translation/package consistency checks and a dedicated workspace file.

## 0.1.0a1

First public alpha: UI configuration, HEMS telemetry/decisions, header-only authentication, measurement validation, EV SOC telemetry, script adapter contract, persistent requested operation, verified Auto recovery and regression tests.

No turnkey inverter driver or EV/load actuation yet. No production HA configuration is migrated automatically.
