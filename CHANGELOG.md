# Changelog

## 0.1.0a7

- Document the optional `load_power_w` request field and the fields of `loads[]` entries, including `on`/`off` for deferrable loads and `reports_power`; add proposal 5 on deferrable-load actuation and measured power. This alpha does not actuate loads and does not send `load_power_w`.
- Keep HEMS Client hardware-neutral: adapter failures retain the HEMS desired state and report receipt status locally; the client no longer issues an automatic `auto` fallback or retry command.
- Add a documented Fronius GEN24 adapter example with a public apply/verify-script shape and no site-specific entities, registers or limits.
- Resolve a selected script entity through the Home Assistant entity registry so a customized entity ID can still call its YAML script service and return a receipt.

## 0.1.0a6

- Document the optional `ev_power_by_uid` request field and the service's charger check in the protocol; add proposal 4 on charger current control. No client change; this alpha does not actuate loads.

## 0.1.0a5

- Document the optional charger identifier `uid` on charger loads and the optional `ev_chargers` list in the response. No client change is required; this alpha ignores both.

## 0.1.0a4

- Schedule healthy telemetry every 20 seconds independently of command interval metadata.
- Expose adapter capabilities and retain an explicit unsupported-command error through Auto recovery without repeated unsupported writes.
- Preserve self-consumption discharge ceilings independently of EV telemetry. Device-specific mode selection remains in adapter scripts; existing adapters must implement the ceiling contract.
- Document nighttime measurement requirements without fabricating zero solar production.

## 0.1.0a3

EV SOC freshness is now owned by the source integration. Removed the EV SOC timeout and timestamp selectors, added English/Swedish guidance, and retained numeric/range validation. Existing timeout/timestamp options are ignored. Scheduled sampling is explicitly marked as an HA event-loop callback.

## 0.1.0a2

Swedish and English config/options, entity names, decision/execution/connection states, command selectors and user-facing adapter errors. Added HACS validation, translation/package consistency checks and a dedicated workspace file.

## 0.1.0a1

First public alpha: UI configuration, HEMS telemetry/decisions, header-only authentication, measurement validation, EV SOC telemetry, script adapter contract, persistent requested operation, verified Auto recovery and regression tests.

No turnkey inverter driver or EV/load actuation yet. No production HA configuration is migrated automatically.
