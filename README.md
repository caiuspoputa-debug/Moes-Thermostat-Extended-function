# Moes Relay Heating

Home Assistant custom integration that uses a `climate` thermostat as the control source and a `switch` relay as the heating output.

## Version 0.0.1

For each zone you select directly from the Home Assistant UI:

- one `climate` thermostat;
- one `switch` relay;
- a start hysteresis, default `1.0°C`.

No entity IDs need to be typed manually.

## Control logic

Example:

```text
TARGET = 23.0°C
HYSTERESIS = 1.0°C

CURRENT <= 22.0°C  -> relay ON
CURRENT >= 23.0°C  -> relay OFF
22.0°C < CURRENT < 23.0°C -> keep previous relay demand
```

The thermostat must be in `heat` mode. Any other HVAC mode requests relay OFF.

## Safety

Relay is forced OFF when:

- thermostat entity is missing;
- thermostat is unavailable/unknown;
- current temperature is missing;
- target temperature is missing.

## Heat demand entity

Each configured zone creates:

```text
binary_sensor.<zone>_cerere_caldura
```

Its attributes include:

- current temperature;
- target temperature;
- ON threshold;
- hysteresis;
- thermostat mode;
- relay state;
- reason for current decision.

## Restart behavior

The last heat-demand state is stored. If Home Assistant restarts while temperature is inside the hysteresis band, the previous demand is preserved instead of creating a false ON/OFF transition.

## Brand

Home Assistant local branding is included at:

```text
custom_components/moes_relay_heating/brand/icon.png
custom_components/moes_relay_heating/brand/icon@2x.png
```

## Local operation

This integration itself only talks to Home Assistant entities. If both the selected thermostat and relay are available locally in Home Assistant, control can continue without WAN/internet access.
