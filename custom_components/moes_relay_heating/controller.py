"""Heating demand logic and relay control."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_TEMPERATURE,
    CONF_HYSTERESIS,
    CONF_RELAY,
    CONF_THERMOSTAT,
    CONF_ZONE_NAME,
    DEFAULT_HYSTERESIS,
    DOMAIN,
    MODE_HEAT,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class HeatingController:
    """Generate heat demand from a climate entity and control one relay."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        cfg = {**entry.data, **entry.options}
        self.zone_name: str = cfg.get(CONF_ZONE_NAME, entry.title)
        self.thermostat: str = cfg[CONF_THERMOSTAT]
        self.relay: str = cfg[CONF_RELAY]
        self.hysteresis: float = float(
            cfg.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
        )

        self.heat_demand: bool = False
        self.current_temperature: float | None = None
        self.target_temperature: float | None = None
        self.turn_on_below: float | None = None
        self.thermostat_mode: str | None = None
        self.reason: str = "startup"

        self._listeners: list[Callable[[], None]] = []
        self._unsub = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    async def async_start(self) -> None:
        """Restore state, subscribe to changes and evaluate immediately."""
        stored = await self._store.async_load() or {}
        stored_demand = stored.get("heat_demand")
        if isinstance(stored_demand, bool):
            self.heat_demand = stored_demand

        self._unsub = async_track_state_change_event(
            self.hass,
            [self.thermostat, self.relay],
            self._state_changed,
        )

        await self._evaluate_and_apply(trigger="startup")
        _LOGGER.info(
            "[%s] Started: thermostat=%s relay=%s hysteresis=%.1f demand=%s",
            self.zone_name,
            self.thermostat,
            self.relay,
            self.hysteresis,
            self.heat_demand,
        )

    async def async_stop(self) -> None:
        """Stop listeners. Relay state is left unchanged on unload."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register entity update callback."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def _state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        if entity_id == self.thermostat:
            self.hass.async_create_task(
                self._evaluate_and_apply(trigger="thermostat")
            )
        elif entity_id == self.relay:
            # If someone changes the relay manually, re-assert the controller's
            # desired state whenever the thermostat data is still valid.
            self.hass.async_create_task(
                self._evaluate_and_apply(trigger="relay")
            )

    async def _evaluate_and_apply(self, trigger: str) -> None:
        thermostat = self.hass.states.get(self.thermostat)

        desired, valid = self._calculate_demand(thermostat)

        changed = desired != self.heat_demand
        self.heat_demand = desired

        if changed:
            await self._store.async_save({"heat_demand": self.heat_demand})

        if valid:
            await self._apply_relay()
        else:
            # Safety rule: invalid/missing thermostat data means relay OFF.
            await self._force_relay_off()

        self._notify()

        _LOGGER.debug(
            "[%s] trigger=%s mode=%s current=%s target=%s on_below=%s "
            "demand=%s reason=%s",
            self.zone_name,
            trigger,
            self.thermostat_mode,
            self.current_temperature,
            self.target_temperature,
            self.turn_on_below,
            self.heat_demand,
            self.reason,
        )

    def _calculate_demand(self, thermostat: State | None) -> tuple[bool, bool]:
        """Return (desired_demand, thermostat_data_valid)."""
        self.current_temperature = None
        self.target_temperature = None
        self.turn_on_below = None
        self.thermostat_mode = None

        if thermostat is None:
            self.reason = "thermostat_missing"
            return False, False

        if thermostat.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.thermostat_mode = thermostat.state
            self.reason = "thermostat_unavailable"
            return False, False

        self.thermostat_mode = thermostat.state

        current = thermostat.attributes.get(ATTR_CURRENT_TEMPERATURE)
        target = thermostat.attributes.get(ATTR_TEMPERATURE)

        if not isinstance(current, (int, float)):
            self.reason = "current_temperature_missing"
            return False, False

        if not isinstance(target, (int, float)):
            self.reason = "target_temperature_missing"
            return False, False

        self.current_temperature = float(current)
        self.target_temperature = float(target)
        self.turn_on_below = self.target_temperature - self.hysteresis

        # Initial version: only explicit HEAT mode requests heating.
        if self.thermostat_mode != MODE_HEAT:
            self.reason = f"mode_{self.thermostat_mode}"
            return False, True

        # ON threshold:
        # target 23.0 / hysteresis 1.0 -> ON at 22.0 or below.
        if self.current_temperature <= self.turn_on_below:
            self.reason = "below_start_threshold"
            return True, True

        # OFF threshold:
        # target 23.0 -> OFF at 23.0 or above.
        if self.current_temperature >= self.target_temperature:
            self.reason = "target_reached"
            return False, True

        # Between thresholds preserve the previous demand state.
        self.reason = "inside_hysteresis_band"
        return self.heat_demand, True

    async def _apply_relay(self) -> None:
        relay = self.hass.states.get(self.relay)

        if relay is None:
            _LOGGER.warning("[%s] Relay entity missing: %s", self.zone_name, self.relay)
            return

        if relay.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "[%s] Relay unavailable: %s state=%s",
                self.zone_name,
                self.relay,
                relay.state,
            )
            return

        desired_state = STATE_ON if self.heat_demand else STATE_OFF
        if relay.state == desired_state:
            return

        service = "turn_on" if self.heat_demand else "turn_off"
        _LOGGER.info(
            "[%s] Relay %s -> %s (current=%.2f target=%.2f hysteresis=%.2f)",
            self.zone_name,
            self.relay,
            desired_state,
            self.current_temperature,
            self.target_temperature,
            self.hysteresis,
        )
        await self.hass.services.async_call(
            "switch",
            service,
            {"entity_id": self.relay},
            blocking=True,
        )

    async def _force_relay_off(self) -> None:
        relay = self.hass.states.get(self.relay)
        if relay is None or relay.state != STATE_ON:
            return

        self.heat_demand = False
        await self._store.async_save({"heat_demand": False})

        _LOGGER.warning(
            "[%s] Safety OFF: relay %s switched off because thermostat data is invalid",
            self.zone_name,
            self.relay,
        )
        await self.hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": self.relay},
            blocking=True,
        )
