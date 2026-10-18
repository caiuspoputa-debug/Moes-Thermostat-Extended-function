"""Binary sensor exposing heating demand."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .controller import HeatingController


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up heat demand entity."""
    controller: HeatingController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HeatDemandBinarySensor(controller, entry)])


class HeatDemandBinarySensor(BinarySensorEntity):
    """Shows whether the zone currently requests heat."""

    _attr_has_entity_name = True
    _attr_name = "Cerere căldură"

    def __init__(self, controller: HeatingController, entry: ConfigEntry) -> None:
        self.controller = controller
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_heat_demand"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=controller.zone_name,
            manufacturer="OpenAI / Community",
            model="Moes Relay Heating Controller",
        )
        self._remove_listener = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        self._remove_listener = self.controller.add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Remove controller update listener."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @property
    def is_on(self) -> bool:
        return self.controller.heat_demand

    @property
    def icon(self) -> str:
        return "mdi:radiator" if self.is_on else "mdi:radiator-disabled"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "zone_name": self.controller.zone_name,
            "thermostat": self.controller.thermostat,
            "thermostat_mode": self.controller.thermostat_mode,
            "current_temperature": self.controller.current_temperature,
            "target_temperature": self.controller.target_temperature,
            "turn_on_below": self.controller.turn_on_below,
            "hysteresis": self.controller.hysteresis,
            "reason": self.controller.reason,
        }
