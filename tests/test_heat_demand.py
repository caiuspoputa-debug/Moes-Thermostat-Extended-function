"""Runtime regressions for demand-only operation and existing entity identity."""

from __future__ import annotations

from pathlib import Path
import types
import unittest
from unittest.mock import Mock

try:
    from .ha_stubs import FakeEntry, FakeHass, FakeState, load_integration
except ImportError:
    from ha_stubs import FakeEntry, FakeHass, FakeState, load_integration


ROOT = Path(__file__).resolve().parents[1]
CURRENT = load_integration(ROOT, "moes_demand_current_tests")
THERMOSTAT = "climate.dormitor"
DATA = {"zone_name": "Dormitor", "thermostat": THERMOSTAT, "hysteresis": 1.0}
# These identity values were verified against the actual 0.0.1 entity class.
# Keep the regression portable: it does not require the old ZIP beside it.
ORIGINAL_DOMAIN = "moes_relay_heating"
ORIGINAL_STORAGE_VERSION = 1


def thermostat(current=21.0, target=23.0, mode="heat"):
    return FakeState(mode, current_temperature=current, temperature=target)


class ForbiddenRelay:
    def __str__(self):
        raise AssertionError("An obsolete relay option must never be used")

    def __bool__(self):
        raise AssertionError("An obsolete relay option must never be evaluated")


class DemandControllerTests(unittest.IsolatedAsyncioTestCase):
    async def make_controller(self, state=None, *, data=None, options=None, stored=None):
        entry = FakeEntry(data or DATA, options)
        key = "moes_relay_heating." + entry.entry_id
        storage = {key: stored} if stored is not None else {}
        hass = FakeHass({THERMOSTAT: state or thermostat()}, storage)
        controller = CURRENT.controller.HeatingController(hass, entry)
        await controller.async_start()
        self.addAsyncCleanup(controller.async_stop)
        return hass, entry, controller

    async def test_new_entry_without_relay_starts_and_listens_only_to_thermostat(self):
        hass, entry, controller = await self.make_controller()
        self.assertTrue(controller.heat_demand)
        self.assertEqual([s.entities for s in hass.subscriptions], [[THERMOSTAT]])
        self.assertEqual(hass.states.reads, [THERMOSTAT])
        hass.services.async_call.assert_not_awaited()

    async def test_legacy_relay_data_and_options_are_ignored_for_valid_and_invalid_states(self):
        data, options = {**DATA, "relay": ForbiddenRelay()}, {"relay": ForbiddenRelay()}
        hass, entry, controller = await self.make_controller(data=data, options=options)
        self.assertTrue(controller.heat_demand)
        await hass.state_changed(THERMOSTAT, thermostat(current=24))
        self.assertFalse(controller.heat_demand)
        await hass.state_changed(THERMOSTAT, FakeState("unavailable"))
        self.assertFalse(controller.heat_demand)
        await hass.state_changed("switch.obsolete_relay", FakeState("unavailable"))
        controller._state_changed(types.SimpleNamespace(data={"entity_id": "switch.obsolete_relay"}))
        self.assertEqual(hass.tasks, [])
        self.assertEqual([s.entities for s in hass.subscriptions], [[THERMOSTAT]])
        self.assertTrue(all(entity == THERMOSTAT for entity in hass.states.reads))
        hass.services.async_call.assert_not_awaited()

    async def test_hysteresis_boundaries_and_latched_band_from_actual_state_events(self):
        hass, entry, controller = await self.make_controller(thermostat(current=23.0))
        self.assertFalse(controller.heat_demand)
        for temperature, expected, reason in [
            (22.5, False, "inside_hysteresis_band"),
            (22.0, True, "below_start_threshold"),
            (22.5, True, "inside_hysteresis_band"),
            (23.0, False, "target_reached"),
            (21.9, True, "below_start_threshold"),
            (23.1, False, "target_reached"),
        ]:
            with self.subTest(current=temperature, expected=expected):
                await hass.state_changed(THERMOSTAT, thermostat(current=temperature))
                self.assertEqual(controller.heat_demand, expected)
                self.assertEqual(controller.reason, reason)
        self.assertEqual(controller.turn_on_below, 22.0)
        hass.services.async_call.assert_not_awaited()

    async def test_off_and_other_modes_clear_demand_even_below_start_threshold(self):
        hass, entry, controller = await self.make_controller()
        for mode in ("off", "auto", "cool"):
            with self.subTest(mode=mode):
                await hass.state_changed(THERMOSTAT, thermostat(current=19.0, mode=mode))
                self.assertFalse(controller.heat_demand)
                self.assertEqual(controller.reason, "mode_" + mode)
        hass.services.async_call.assert_not_awaited()

    async def test_missing_unavailable_and_invalid_temperatures_clear_demand_without_services(self):
        hass, entry, controller = await self.make_controller()
        samples = [
            (None, "thermostat_missing"),
            (FakeState("unavailable"), "thermostat_unavailable"),
            (FakeState("unknown"), "thermostat_unavailable"),
            (FakeState("heat", temperature=23), "current_temperature_missing"),
            (thermostat(current="21.0"), "current_temperature_missing"),
            (FakeState("heat", current_temperature=21), "target_temperature_missing"),
            (thermostat(target="23.0"), "target_temperature_missing"),
        ]
        for state, reason in samples:
            with self.subTest(reason=reason, state=state):
                await hass.state_changed(THERMOSTAT, thermostat(current=20))
                self.assertTrue(controller.heat_demand)
                await hass.state_changed(THERMOSTAT, state)
                self.assertFalse(controller.heat_demand)
                self.assertEqual(controller.reason, reason)
        hass.services.async_call.assert_not_awaited()

    async def test_startup_restores_previous_boolean_inside_hysteresis_band(self):
        for demand in (False, True):
            with self.subTest(stored_demand=demand):
                hass, entry, controller = await self.make_controller(
                    thermostat(current=22.5), stored={"heat_demand": demand}
                )
                self.assertEqual(controller.heat_demand, demand)
                self.assertEqual(controller.reason, "inside_hysteresis_band")
                self.assertEqual(controller._store.key, "moes_relay_heating." + entry.entry_id)
                self.assertEqual(controller._store.version, ORIGINAL_STORAGE_VERSION)
                self.assertEqual(controller._store.loads, 1)
                self.assertEqual(controller._store.saves, [])

    async def test_startup_reevaluates_restored_state_and_persists_changes(self):
        for initial, current, desired in [(True, 23, False), (False, 22, True)]:
            with self.subTest(stored=initial, current=current):
                hass, entry, controller = await self.make_controller(
                    thermostat(current=current), stored={"heat_demand": initial}
                )
                self.assertEqual(controller.heat_demand, desired)
                self.assertEqual(controller._store.saves, [{"heat_demand": desired}])
                self.assertEqual(hass.storage[controller._store.key], {"heat_demand": desired})
                hass.services.async_call.assert_not_awaited()

    async def test_nonboolean_stored_state_is_not_treated_as_previous_demand(self):
        hass, entry, controller = await self.make_controller(
            thermostat(current=22.5), stored={"heat_demand": "true"}
        )
        self.assertFalse(controller.heat_demand)

    async def test_options_hysteresis_overrides_data_with_same_original_threshold_rules(self):
        hass, entry, controller = await self.make_controller(
            thermostat(current=21.5), options={"hysteresis": 2.0}
        )
        self.assertEqual(controller.hysteresis, 2.0)
        self.assertEqual(controller.turn_on_below, 21.0)
        self.assertFalse(controller.heat_demand)
        await hass.state_changed(THERMOSTAT, thermostat(current=21.0))
        self.assertTrue(controller.heat_demand)


class EntityIdentityAndSetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_binary_entity_identity_matches_0001_exactly_and_has_no_relay_attributes(self):
        entry = FakeEntry({**DATA, "relay": "switch.old"})
        hass = FakeHass({THERMOSTAT: thermostat()})
        controller = CURRENT.controller.HeatingController(hass, entry)
        await controller.async_start()
        self.addAsyncCleanup(controller.async_stop)
        new = CURRENT.binary_sensor.HeatDemandBinarySensor(controller, entry)
        self.assertEqual(new.unique_id, entry.entry_id + "_heat_demand")
        self.assertEqual(new.name, "Cerere căldură")
        self.assertIs(new.has_entity_name, True)
        self.assertEqual(new.device_info, {
            "identifiers": {("moes_relay_heating", entry.entry_id)},
            "name": "Dormitor",
            "manufacturer": "OpenAI / Community",
            "model": "Moes Relay Heating Controller",
        })
        self.assertEqual(CURRENT.const.DOMAIN, ORIGINAL_DOMAIN)
        self.assertNotIn("relay", new.extra_state_attributes)
        self.assertNotIn("relay_state", new.extra_state_attributes)
        self.assertEqual(set(new.extra_state_attributes), {
            "zone_name", "thermostat", "thermostat_mode", "current_temperature",
            "target_temperature", "turn_on_below", "hysteresis", "reason",
        })
        self.assertTrue(new.is_on)
        self.assertEqual(new.icon, "mdi:radiator")
        hass.services.async_call.assert_not_awaited()

    async def test_entity_subscribes_to_demand_updates_and_removes_its_listener(self):
        entry = FakeEntry(DATA)
        hass = FakeHass({THERMOSTAT: thermostat()})
        controller = CURRENT.controller.HeatingController(hass, entry)
        await controller.async_start()
        self.addAsyncCleanup(controller.async_stop)
        entity = CURRENT.binary_sensor.HeatDemandBinarySensor(controller, entry)
        await entity.async_added_to_hass()
        await hass.state_changed(THERMOSTAT, thermostat(current=23))
        self.assertEqual(entity.writes, 1)
        self.assertFalse(entity.is_on)
        self.assertEqual(entity.icon, "mdi:radiator-disabled")
        await entity.async_will_remove_from_hass()
        await hass.state_changed(THERMOSTAT, thermostat(current=21))
        self.assertEqual(entity.writes, 1)

    async def test_setup_unload_preserve_existing_entry_and_other_zone(self):
        entry = FakeEntry({**DATA, "relay": ForbiddenRelay()}, {"relay": ForbiddenRelay()})
        hass = FakeHass({THERMOSTAT: thermostat()})
        other_zone = object()
        hass.data = {CURRENT.const.DOMAIN: {"other-entry": other_zone}}
        original_identity = (entry.entry_id, entry.unique_id, entry.title)
        self.assertTrue(await CURRENT.integration.async_setup_entry(hass, entry))
        self.assertEqual((entry.entry_id, entry.unique_id, entry.title), original_identity)
        self.assertIs(hass.data[CURRENT.const.DOMAIN]["other-entry"], other_zone)
        hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, ["binary_sensor"])
        add_entities = Mock()
        await CURRENT.binary_sensor.async_setup_entry(hass, entry, add_entities)
        entity = add_entities.call_args.args[0][0]
        self.assertEqual(entity.unique_id, entry.entry_id + "_heat_demand")
        self.assertEqual(len(entry.unload_callbacks), 1)
        await entry.update_listener(hass, entry)
        hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
        self.assertTrue(await CURRENT.integration.async_unload_entry(hass, entry))
        self.assertEqual(hass.data[CURRENT.const.DOMAIN], {"other-entry": other_zone})
        self.assertFalse(hass.subscriptions[0].active)
        hass.services.async_call.assert_not_awaited()

    async def test_failed_platform_unload_keeps_existing_controller_running(self):
        entry = FakeEntry(DATA)
        hass = FakeHass({THERMOSTAT: thermostat()})
        await CURRENT.integration.async_setup_entry(hass, entry)
        controller = hass.data[CURRENT.const.DOMAIN][entry.entry_id]
        self.addAsyncCleanup(controller.async_stop)
        hass.config_entries.async_unload_platforms.return_value = False
        self.assertFalse(await CURRENT.integration.async_unload_entry(hass, entry))
        self.assertIs(hass.data[CURRENT.const.DOMAIN][entry.entry_id], controller)
        self.assertTrue(hass.subscriptions[0].active)


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_zone_schema_has_only_zone_thermostat_hysteresis(self):
        flow = CURRENT.flow.MoesRelayHeatingConfigFlow()
        form = await flow.async_step_user()
        keys = {key.schema for key in form["data_schema"].schema}
        self.assertEqual(keys, {"zone_name", "thermostat", "hysteresis"})
        values = {key.schema: value for key, value in form["data_schema"].schema.items()}
        self.assertEqual(values["thermostat"], ("EntitySelector", {"domain": "climate", "multiple": False}))
        self.assertEqual(values["hysteresis"][1], {
            "min": 0.1, "max": 5.0, "step": 0.1, "unit_of_measurement": "°C", "mode": "box",
        })

    async def test_creating_zone_without_relay_keeps_thermostat_unique_id(self):
        flow = CURRENT.flow.MoesRelayHeatingConfigFlow()
        result = await flow.async_step_user(DATA)
        self.assertEqual(result["title"], "Dormitor")
        self.assertEqual(result["data"], DATA)
        self.assertEqual(flow.unique_id, THERMOSTAT)
        self.assertTrue(flow.checked_existing_unique_id)

    async def test_existing_zone_options_hide_legacy_relay_and_keep_other_defaults(self):
        entry = FakeEntry({**DATA, "relay": "switch.old"}, {"hysteresis": 1.7, "relay": "switch.other"})
        flow = CURRENT.flow.MoesRelayHeatingOptionsFlow(entry)
        form = await flow.async_step_init()
        defaults = {key.schema: key.default for key in form["data_schema"].schema}
        self.assertEqual(defaults, {"zone_name": "Dormitor", "thermostat": THERMOSTAT, "hysteresis": 1.7})
        self.assertEqual(await flow.async_step_init({**DATA, "hysteresis": 2.0, "relay": "switch.old"}), {
            "type": "create_entry", "title": "", "data": {**DATA, "hysteresis": 2.0},
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
