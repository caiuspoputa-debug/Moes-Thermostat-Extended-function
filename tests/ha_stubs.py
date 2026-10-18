"""Small Home Assistant stand-ins used only by the isolated regression tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, Mock, patch


class FakeState:
    def __init__(self, state="heat", **attributes):
        self.state = state
        self.attributes = attributes


class FakeStates:
    def __init__(self, initial=None):
        self.values = dict(initial or {})
        self.reads = []

    def get(self, entity_id):
        self.reads.append(entity_id)
        if str(entity_id).startswith("switch."):
            raise AssertionError("The integration must never read a relay state")
        return self.values.get(entity_id)


class FakeStore:
    @classmethod
    def __class_getitem__(cls, value):
        return cls

    def __init__(self, hass, version, key):
        self.hass, self.version, self.key = hass, version, key
        self.loads = 0
        self.saves = []
        hass.stores.append(self)

    async def async_load(self):
        self.loads += 1
        return deepcopy(self.hass.storage.get(self.key))

    async def async_save(self, value):
        self.saves.append(deepcopy(value))
        self.hass.storage[self.key] = deepcopy(value)


def track_state_change(hass, entity_ids, callback):
    subscription = types.SimpleNamespace(entities=list(entity_ids), callback=callback, active=True)
    hass.subscriptions.append(subscription)

    def unsubscribe():
        subscription.active = False

    return Mock(side_effect=unsubscribe)


class FakeHass:
    def __init__(self, states=None, storage=None):
        self.data = {}
        self.states = FakeStates(states)
        self.storage = deepcopy(storage or {})
        self.stores = []
        self.tasks = []
        self.subscriptions = []
        self.services = types.SimpleNamespace(
            async_call=AsyncMock(side_effect=AssertionError("Integration must not command any service"))
        )
        self.config_entries = types.SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
            async_reload=AsyncMock(),
        )

    def async_create_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task

    async def state_changed(self, entity_id, state):
        old = self.states.values.get(entity_id)
        self.states.values[entity_id] = state
        event = types.SimpleNamespace(data={"entity_id": entity_id, "old_state": old, "new_state": state})
        for subscription in list(self.subscriptions):
            if subscription.active and entity_id in subscription.entities:
                subscription.callback(event)
        while self.tasks:
            tasks, self.tasks = self.tasks, []
            await asyncio.gather(*tasks)


class FakeEntry:
    def __init__(self, data, options=None, entry_id="existing-dormitor-entry", title="Dormitor"):
        self.data, self.options = dict(data), dict(options or {})
        self.entry_id, self.title = entry_id, title
        self.unique_id = self.data.get("thermostat")
        self.unload_callbacks = []
        self.update_listener = None

    def add_update_listener(self, callback):
        self.update_listener = callback
        return Mock(name="remove_options_listener")

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)


class FakeBinarySensor:
    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def name(self):
        return self._attr_name

    @property
    def device_info(self):
        return self._attr_device_info

    @property
    def has_entity_name(self):
        return self._attr_has_entity_name

    def async_write_ha_state(self):
        self.writes = getattr(self, "writes", 0) + 1


class FakeFlow:
    def __init_subclass__(cls, **kwargs):
        pass

    async def async_set_unique_id(self, value):
        self.unique_id = value

    def _abort_if_unique_id_configured(self):
        self.checked_existing_unique_id = True

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}


class Required:
    def __init__(self, schema, **kwargs):
        self.schema = schema
        self.default = kwargs.get("default")


class Schema:
    def __init__(self, schema):
        self.schema = schema


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


def stub_modules():
    ha = module("homeassistant")
    config_entries = module("homeassistant.config_entries", ConfigEntry=FakeEntry,
                            ConfigFlow=FakeFlow, OptionsFlow=FakeFlow,
                            OptionsFlowWithConfigEntry=FakeFlow)
    ha.config_entries = config_entries
    selectors = module("homeassistant.helpers.selector")
    for name in ("EntitySelector", "NumberSelector", "TextSelector"):
        setattr(selectors, name, lambda config=None, kind=name: (kind, config))
    selectors.EntitySelectorConfig = lambda **kwargs: kwargs
    selectors.NumberSelectorConfig = lambda **kwargs: kwargs
    selectors.NumberSelectorMode = types.SimpleNamespace(BOX="box")
    helpers = module("homeassistant.helpers", selector=selectors)
    return {
        "homeassistant": ha,
        "homeassistant.config_entries": config_entries,
        "homeassistant.const": module("homeassistant.const", STATE_OFF="off", STATE_ON="on",
                                      STATE_UNAVAILABLE="unavailable", STATE_UNKNOWN="unknown"),
        "homeassistant.core": module("homeassistant.core", Event=object, HomeAssistant=FakeHass,
                                     State=FakeState, callback=lambda fn: fn),
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": module("homeassistant.helpers.event", async_track_state_change_event=track_state_change),
        "homeassistant.helpers.storage": module("homeassistant.helpers.storage", Store=FakeStore),
        "homeassistant.helpers.entity": module("homeassistant.helpers.entity", DeviceInfo=dict),
        "homeassistant.helpers.entity_platform": module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object),
        "homeassistant.helpers.selector": selectors,
        "homeassistant.components": module("homeassistant.components"),
        "homeassistant.components.binary_sensor": module("homeassistant.components.binary_sensor", BinarySensorEntity=FakeBinarySensor),
        "voluptuous": module("voluptuous", Required=Required, Schema=Schema),
    }


def load_integration(root: Path, package: str):
    component = root / "custom_components/moes_relay_heating"
    parent = module(package)
    parent.__path__ = [str(component)]
    sys.modules[package] = parent

    def load(name, filename=None):
        fullname = package if filename == "__init__.py" else package + "." + name
        spec = importlib.util.spec_from_file_location(fullname, component / (filename or name + ".py"))
        value = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = value
        spec.loader.exec_module(value)
        return value

    with patch.dict(sys.modules, stub_modules()):
        const = load("const")
        controller = load("controller")
        binary_sensor = load("binary_sensor")
        flow = load("config_flow")
        integration = load("integration", "__init__.py")
    return types.SimpleNamespace(const=const, controller=controller,
                                 binary_sensor=binary_sensor, flow=flow, integration=integration)
