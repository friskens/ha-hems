# HEMS Client for Home Assistant

A community Home Assistant integration for the HEMS service at
[PowerGravio](https://powergravio.se). HEMS Client collects selected local
measurements, exchanges them with HEMS, and exposes the returned decisions as
Home Assistant entities.

**0.2.0a2 is an experimental, breaking alpha.** It no longer calls scripts or
controls inverters, chargers or loads. Your own Home Assistant automation or
template consumes the HEMS decision and controls the equipment you choose.

[Svenska](docs/INSTALL_SV.md) · [Protocol](docs/PROTOCOL.md) ·
[Contract source](contract/hems-contract.json) · [Local automation migration](docs/LOCAL_AUTOMATION_MIGRATION.md) · [Roadmap](docs/ROADMAP.md)

## How it works

```text
HEMS contract and service → HEMS Client → HEMS decision sensors → your HA automation → your equipment
```

The co-maintainer owns `contract/hems-contract.json`. It defines the telemetry
fields, response fields and action meanings. `docs/PROTOCOL.md` is generated
from that file and CI prevents them from drifting apart.

HEMS Client lets you select existing Home Assistant sensors for the contract's
inputs. It validates those selections, sends telemetry to HEMS, and provides
decision, freshness, connection and informational load/charger entities from
the contract's safe declarative output fields. It
does not create, edit or execute your automations and never calls services that
operate equipment.

## Install through HACS

1. Add `https://github.com/friskens/ha-hems` to HACS as a custom **Integration** repository.
2. Enable prereleases, install a published HEMS Client release, and restart Home Assistant.
3. Add **HEMS Client** under Settings → Devices & services.
4. Enter the provider's HTTPS base address or complete endpoint and API key. A
   base address automatically uses `/battery`; an explicit path is preserved.
5. Select the existing sensors requested by the integration. Resolve any Repair
   that identifies a missing or incompatible source.
6. Create one local automation triggered by `sensor.hems_decision`. Require a
   fresh decision, use a `choose` branch per action and set `mode: restart`.

The default branch is intentionally unavailable in HACS: published GitHub
Releases supply the matching update announcement. This repository is not in the
HACS default catalogue.

## Important migration from 0.1

0.1 adapter scripts are not run by 0.2. Before upgrading an active system,
build and test the automation that should perform each HEMS action. The client
continues to expose `action`, `power_kw`, `power_w`, loads and freshness, but it
does not verify or restore equipment settings.

Use the stable HEMS `uid` for a charger, otherwise `id`, when matching
informational load entities. A short name is display metadata only and may
change. Outputs that are temporarily absent remain registered rather than being
deleted.

## Freshness and diagnostics

HEMS Client sends the last valid value while a source is temporarily slow and
marks it in the request's `stale` list after the contract-defined limit. Missing
data is never fabricated as zero. The client raises Repairs for a missing or
structurally incompatible selected source, not merely because a source is old.

The informational command-followed status is deliberately non-actuating: it can
report following, not following, waiting or unable to tell, but never retries,
changes a decision or writes to an integration.

MIT licensed. No production Home Assistant configuration is migrated
automatically.
