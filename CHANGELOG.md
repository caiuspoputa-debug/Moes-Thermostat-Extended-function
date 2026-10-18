# Changelog

## 0.0.2 — Heat-demand output without direct relay control

- Remove relay selection from setup and options. Keep only `zone_name`,
  `thermostat` and `hysteresis`.
- Ignore legacy saved relay configuration; it is no longer required for an
  existing entry to load.
- Remove all direct relay commands, relay-state monitoring/reassertion and
  relay output attributes. Invalid thermostat data does not send a relay OFF
  or any other relay command.
- Preserve the existing **Cerere căldură** binary sensor and heat-demand logic:
  in `heat`, ON at `current <= target - hysteresis`, OFF at `current >= target`,
  and retain the previous demand between the thresholds. Other modes or invalid
  thermostat data produce demand OFF only.
- Keep the integration name **Moes Relay Heating**, domain
  `moes_relay_heating`, existing entity names/IDs, entity unique IDs, device
  identifiers, config-entry identity and stored demand state unchanged.
- Update by replacing the component and restarting Home Assistant. No entry
  deletion/recreation or entity renaming is required.
- Keep the HACS integration layout. No automations are included or installed
  by this integration package.
- Final local validation is pending. No Home Assistant installation or test
  on real heating equipment was performed for this build.

## 0.0.1 — Historical initial version

- Calculated heat demand from a `climate` thermostat with start hysteresis and
  stored the previous demand for restart recovery.
- Exposed the **Cerere căldură** binary sensor.
- Included direct relay selection and control; those functions are removed
  in 0.0.2.
