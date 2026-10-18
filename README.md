# Moes Relay Heating

Home Assistant custom integration that calculates heating demand from a
`climate` thermostat and exposes the existing **Cerere căldură** binary sensor.
The integration name remains **Moes Relay Heating** for compatibility.

## Version 0.0.2

Relay selection and all direct relay control have been removed. Existing relay
configuration is ignored and is not required to load an existing zone. The
integration sends no commands to any relay, including an OFF command when
thermostat data is invalid, during startup, or during shutdown.

The three zone settings are:

| Setting | Purpose |
| --- | --- |
| `zone_name` | Existing zone name |
| `thermostat` | Source `climate` entity, selected in the UI |
| `hysteresis` | Start hysteresis, default `1.0°C` |

No relay field is shown in setup or options. Relay behavior is outside this
integration. This package contains only the integration, its documentation and
its own validation files; it does not contain or install automations.

## Heat-demand logic

The calculation is unchanged. With the thermostat in `heat` mode:

```text
TARGET = 23.0°C
HYSTERESIS = 1.0°C

CURRENT <= 22.0°C -> Cerere căldură ON
CURRENT >= 23.0°C -> Cerere căldură OFF
22.0°C < CURRENT < 23.0°C -> preserve previous heat demand
```

In general, demand turns ON at `current <= target - hysteresis`, turns OFF at
`current >= target`, and retains its previous value between those thresholds.

Any other HVAC mode makes demand OFF. A missing, unknown or unavailable
thermostat, or a missing current/target temperature, also makes demand OFF.
These are binary-sensor decisions only; no relay is switched or forced OFF.

## Existing entity and identity

The output keeps its existing name **Cerere căldură**. The integration does not
rename existing entities, assign a new `entity_id`, or create a replacement
sensor on update. Existing Home Assistant names, entity IDs and history remain
associated with the same entity.

Compatibility identifiers remain unchanged:

- integration domain: `moes_relay_heating`;
- entity unique ID: `<entry.entry_id>_heat_demand`;
- device identifier: `(moes_relay_heating, entry.entry_id)`;
- existing config-entry identity and stored heat-demand state.

The binary sensor continues to expose:

- zone name and source thermostat;
- current temperature;
- target temperature;
- ON threshold;
- hysteresis;
- thermostat mode;
- reason for current decision.

Relay selection and relay-state attributes are no longer part of this output.

## Restart behavior

The last heat-demand state is stored as before. If Home Assistant restarts while
temperature is inside the hysteresis band, the previous demand is preserved.
The existing storage identity is retained; no entry recreation is required.

## Installation and update

The repository layout includes `hacs.json` and the component folder for HACS.
For an existing HACS installation, update the component through its existing
repository when version `0.0.2` is available, then restart Home Assistant.

For a manual update, back up the installed component and replace
`/config/custom_components/moes_relay_heating` with the package's
`custom_components/moes_relay_heating` folder. Restart Home Assistant and check
the installed manifest reports `0.0.2` and that the integration loads.

Keep existing integration entries and zone names. Do not delete/recreate an
entry or rename entities to update this version. Old relay fields in saved
configuration are ignored. See [INSTALL_RO.md](INSTALL_RO.md) for Romanian
instructions and [CHANGELOG.md](CHANGELOG.md) for the changes.

## Brand

Home Assistant local branding is included at:

```text
custom_components/moes_relay_heating/brand/icon.png
custom_components/moes_relay_heating/brand/icon@2x.png
```

## Local operation

The integration reads the selected thermostat's state from Home Assistant and
calculates demand locally. It does not require its own internet connection;
thermostat availability still depends on the integration providing that entity.

## Validation status

All 16 local behavioral tests passed, with no failures or skipped tests.
Entity identity, unchanged hysteresis, legacy configuration and absence of
relay reads/commands were checked. See TEST_REPORT.json and TEST_LOG.txt. This package has not been
installed on Home Assistant or validated on real heating equipment in this
session. Local tests do not establish real-device behavior.
