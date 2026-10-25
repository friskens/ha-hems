<!-- GENERATED FILE — do not edit directly. Source: contract/hems-contract.json; run python scripts/generate_protocol.py -->

# HEMS protocol

**Contract:** `hems-battery-exchange`
**Contract version:** `1`

Machine-readable form of docs/PROTOCOL.md: the data exchanged with POST /battery and how HEMS Client maps it to Home Assistant entities. Interface only. Rules are local data transformations in the client; they never describe how the service decides.

## Source of truth

This document is generated from `contract/hems-contract.json`. Change the JSON contract, run the generator, and commit both files. CI rejects a stale generated document.

## Exchange

| Property | Value |
| --- | --- |
| Method | `POST` |
| Path | `/battery` |
| Auth header | `X-Api-Key` |
| Owner | `engine` |
| Unknown response fields | `ignore` |
| Max response bytes | `65536` |

### Cadence

- **Every s:** `20`
- **Also at quarter hour:** `true`
- **Min spacing s:** `20`
- **Backoff after failure s:** `60`

## Request inputs

### `battery_soc`

- **Field:** `soc`
- **Required:** `true`
- **Domain:** `sensor`
- **Device class:** `battery`
- **Unit:** `%`
- **Repair if missing:** `true`
- **Stale after s:** `null`

### `grid_power`

- **Field:** `grid_power`
- **Required:** `true`
- **Domain:** `sensor`
- **Device class:** `power`
#### Units

`W`, `kW`
- **Repair if missing:** `true`
#### Options

`invert`
- **Stale after s:** `null`

### `battery_power`

- **Field:** `battery_power`
- **Required:** `true`
- **Domain:** `sensor`
- **Device class:** `power`
#### Units

`W`, `kW`
- **Repair if missing:** `true`
#### Options

`invert`
- **Stale after s:** `null`

### `solar_sources`

- **Field:** `solar_power`
- **Required:** `true`
- **Multiple:** `true`
- **Domain:** `sensor`
- **Device class:** `power`
#### Units

`W`, `kW`
- **Repair if missing:** `true`
- **Stale after s:** `null`

### `ev_power`

- **Field:** `ev_power_w`
- **Required:** `false`
- **Domain:** `sensor`
- **Device class:** `power`
#### Units

`W`, `kW`
- **Stale after s:** `null`

### `ev_soc`

- **Field:** `ev_soc_pct`
- **Required:** `false`
- **Domain:** `sensor`
- **Device class:** `battery`
- **Unit:** `%`
- **Stale after s:** `null`

### `grid_meter_current_l1`

- **Field:** `phase_current_a`
- **Index:** `0`
- **Required:** `false`
- **Group:** `phase_current`
- **Domain:** `sensor`
- **Device class:** `current`
#### Units

`A`, `mA`
- **Label hint:** `Grid meter at the connection point, not inverter output current`
- **Stale after s:** `null`

### `grid_meter_current_l2`

- **Field:** `phase_current_a`
- **Index:** `1`
- **Required:** `false`
- **Group:** `phase_current`
- **Domain:** `sensor`
- **Device class:** `current`
#### Units

`A`, `mA`
- **Stale after s:** `null`

### `grid_meter_current_l3`

- **Field:** `phase_current_a`
- **Index:** `2`
- **Required:** `false`
- **Group:** `phase_current`
- **Domain:** `sensor`
- **Device class:** `current`
#### Units

`A`, `mA`
- **Stale after s:** `null`

### `load_power`

- **Field:** `load_power_w`
- **Keyed by:** `loads[].id where kind = deferrable`
- **Required:** `false`
- **Per output entry:** `true`
- **Domain:** `sensor`
- **Device class:** `power`
#### Units

`W`, `kW`
- **Client status:** `not_sent`
- **Stale after s:** `null`

## Local transformation rules

### `to_watts`

#### Applies to

`grid_power`, `battery_power`, `solar_sources`, `ev_power`, `load_power`
- **Expression:** `value * 1000 if unit == 'kW' else value`

### `to_amps`

#### Applies to

`grid_meter_current_l1`, `grid_meter_current_l2`, `grid_meter_current_l3`
- **Expression:** `value / 1000 if unit == 'mA' else value`

### `invert`

#### Applies to

`grid_power`, `battery_power`
- **Expression:** `-value if option.invert else value`
#### Result sign

- **Grid power:** `import positive`
- **Battery power:** `charge positive`

### `sum_solar`

#### Applies to

`solar_sources`
- **Expression:** `sum(values)`
- **All sources required:** `true`

### `phase_magnitude`

#### Applies to

`grid_meter_current_l1`, `grid_meter_current_l2`, `grid_meter_current_l3`
- **Expression:** `abs(value)`
- **Round:** `1`

### `phase_group`

- **Group:** `phase_current`
- **Send as:** `[L1, L2, L3]`
- **All or none:** `true`
#### Range

`0`, `250`

### `constants`

- **Heartbeat:** `false`
- **App version:** `ha-hems/<version>`

### `mark_stale`

- **Field:** `stale`
- **After s:** `null`
#### When source state

`unavailable`, `unknown`
- **Expression:** `names of the request fields whose selected source is unavailable, unknown or not a valid number; a field built from several sources is stale while any of them is`
- **Age is not staleness:** `a valid state that has not changed or has not been reported again is current; neither last_changed nor last_reported age marks a field stale`
- **Send last known value:** `true`
- **Never blocks exchange:** `true`
- **Skip exchange only if:** `a required input has had no value since start`

### `never_fabricate_zero`

- **Applies to:** `all inputs`
- **Expression:** `a missing or invalid measurement is omitted, never sent as 0`

## Response outputs

### `decision`

- **Entity:** `sensor`
- **State from:** `action`
#### Values

`charge`, `chargesolar`, `selfconsumption`, `sellsolar`, `pause`, `export`, `peakshaving`, `zeroexport`, `observe`
- **Core:** `true`
- **On invalid:** `reject_response`
#### Attributes

##### Power kw

- **Type:** `number`
- **Min:** `0`
- **Core:** `true`
###### Required for

`charge`, `chargesolar`, `export`, `peakshaving`, `selfconsumption`
- **Default otherwise:** `0`
- **On invalid:** `reject_response`
- **Note:** `For selfconsumption: maximum battery discharge, 0 blocks discharge.`
##### Power w

- **From:** `power_kw`
- **Expression:** `power_kw * 1000`
- **Local:** `true`
##### Command interval seconds

- **Type:** `integer`
- **Min:** `1`
- **Core:** `true`
- **On invalid:** `reject_response`
##### Power

- **Type:** `number`
- **Presentation only:** `true`
- **On invalid:** `reject_response`
##### Power unit

- **Type:** `enum`
###### Values

`w`, `kw`
- **On invalid:** `reject_response`
##### Soc

- **Type:** `number`
- **Min:** `0`
- **Max:** `100`
- **Informational:** `true`
- **On invalid:** `reject_response`
##### Received at

- **Local:** `true`
- **Required:** `true`
##### Fresh

- **Local:** `true`
- **Required:** `true`
- **Expression:** `now - received_at < 90`
- **Note:** `Automations must not act on a decision that is not fresh.`
#### Names

- **Sv:** `HEMS beslut`
- **En:** `HEMS decision`
- **Unique id:** `decision`
- **Icon:** `mdi:battery-sync`
#### Extra entities

##### Power target

- **From:** `attributes.power_w`
- **Entity:** `sensor`
###### Names

- **Sv:** `HEMS effektmål`
- **En:** `HEMS power target`
- **Unique id:** `power_target`
- **Device class:** `power`
- **Unit:** `W`
- **State class:** `measurement`
##### Decision fresh

- **From:** `attributes.fresh`
- **Entity:** `binary_sensor`
###### Names

- **Sv:** `HEMS beslut färskt`
- **En:** `HEMS decision fresh`
- **Unique id:** `decision_fresh`
##### Command interval

- **From:** `attributes.command_interval_seconds`
- **Entity:** `sensor`
###### Names

- **Sv:** `HEMS kommandointervall`
- **En:** `HEMS command interval`
- **Unique id:** `command_interval`
- **Device class:** `duration`
- **Unit:** `s`
- **Entity category:** `diagnostic`
#### Action meaning

##### Charge

- **En:** `Charge the battery at the power target; solar allowed; no discharge.`
- **Power:** `charge power`
##### Chargesolar

- **En:** `Charge from solar only, up to the power target; no discharge.`
- **Power:** `maximum solar charge power`
##### Selfconsumption

- **En:** `Normal self-consumption; the power target is the maximum battery discharge.`
- **Power:** `discharge ceiling, 0 blocks discharge`
##### Pause

- **En:** `No discharge; surplus solar may charge the battery.`
- **Power:** `not used`
##### Sellsolar

- **En:** `Export solar; the battery neither charges nor discharges.`
- **Power:** `not used`
##### Export

- **En:** `Controlled net export to the grid at the power target.`
- **Power:** `net export power`
##### Peakshaving

- **En:** `The battery covers the whole house load so that grid import stays at zero. A fixed import limit above zero does not meet this.`
- **Power:** `expected discharge power; following it, or holding grid import at zero, are both valid`
##### Zeroexport

- **En:** `No export to the grid.`
- **Power:** `not used`
##### Observe

- **En:** `Do nothing; leave the equipment as it is.`
- **Power:** `not used`

### `loads`

- **Entity:** `attribute_of_decision`
- **Recorder:** `false`
- **From:** `loads`
- **Null means:** `no list supplied`
- **Empty means:** `no entries, not switch everything off`
- **On invalid:** `reject_response`
#### Entry

##### Id

- **Type:** `string`
- **Non empty:** `true`
- **Unique in list:** `true`
- **Required:** `true`
- **On invalid:** `reject_response`
##### Action

- **Type:** `string`
- **Non empty:** `true`
- **Required:** `true`
###### Values by kind

###### Ev

`charge`, `stop`
###### Deferrable

`on`, `off`
- **On invalid:** `reject_response`
##### Kind

- **Type:** `enum`
###### Values

`ev`, `deferrable`
- **On invalid:** `omit_field`
##### Name

- **Type:** `string`
- **On invalid:** `omit_field`
##### Reason

- **Type:** `string`
- **Display only:** `true`
- **Never parse:** `true`
- **On invalid:** `omit_field`
##### Power kw

- **Type:** `number`
- **Min:** `0`
- **On invalid:** `reject_response`
##### Power w

- **Type:** `number`
- **Min:** `0`
- **On invalid:** `omit_field`
##### Current a

- **Type:** `number`
- **Min:** `0`
- **Kind:** `ev`
- **On invalid:** `reject_response`
##### Target pct

- **Type:** `number`
- **Min:** `0`
- **Max:** `100`
- **Kind:** `ev`
- **On invalid:** `reject_response`
##### Uid

- **Type:** `string`
- **Kind:** `ev`
- **Stable:** `true`
- **On invalid:** `omit_field`
##### Reports power

- **Type:** `boolean`
- **Kind:** `deferrable`
- **On invalid:** `omit_field`
##### Enabled

- **Type:** `boolean`
- **Kind:** `deferrable`
- **Meaning of false:** `customer turned off the service's control of this load`
- **On invalid:** `omit_field`
#### Entity per entry

- **Entity:** `sensor`
- **State from:** `action`
- **Unique id:** `load_{uid or id}`
##### Names

- **Sv:** `{name}`
- **En:** `{name}`
##### Fallback names

- **Sv:** `HEMS last {id}`
- **En:** `HEMS load {id}`
##### Attributes from entry

`kind`, `power_w`, `current_a`, `target_pct`, `reason`, `enabled`, `reports_power`
- **Remove when absent:** `after the entry has been missing from {n} consecutive responses (client decides n)`
- **Note:** `name is the customer's own label from the service; uid (chargers) or id (deferrable loads) keeps the entity stable when the name changes.`

### `ev_chargers`

- **Entity:** `attribute_of_decision`
- **From:** `ev_chargers`
- **Informational:** `true`
- **On invalid:** `omit_field`
#### Entry

##### Id

- **Type:** `string`
##### Uid

- **Type:** `string`
##### Name

- **Type:** `string`
##### Phases

- **Type:** `integer`
- **Min:** `1`
- **Max:** `3`

### `connection`

- **Entity:** `sensor`
- **Local:** `true`
- **Expression:** `connected if exchange_age < 150 else warning if exchange_age < 600 else disconnected`
#### Names

- **Sv:** `HEMS anslutning`
- **En:** `HEMS connection`
- **Unique id:** `connection`
- **Entity category:** `diagnostic`
