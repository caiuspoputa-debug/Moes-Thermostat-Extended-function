"""Config flow for Moes Relay Heating."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_HYSTERESIS,
    CONF_THERMOSTAT,
    CONF_ZONE_NAME,
    DEFAULT_HYSTERESIS,
    DOMAIN,
)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}

    thermostat_key = (
        vol.Required(CONF_THERMOSTAT, default=defaults[CONF_THERMOSTAT])
        if defaults.get(CONF_THERMOSTAT)
        else vol.Required(CONF_THERMOSTAT)
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_ZONE_NAME,
                default=defaults.get(CONF_ZONE_NAME, "Încălzire"),
            ): selector.TextSelector(),
            thermostat_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate", multiple=False)
            ),
            vol.Required(
                CONF_HYSTERESIS,
                default=defaults.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.1,
                    max=5.0,
                    step=0.1,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _supported_data(user_input: dict[str, Any]) -> dict[str, Any]:
    """Save only zone inputs; ignore relay fields from legacy clients."""
    return {
        key: user_input[key]
        for key in (CONF_ZONE_NAME, CONF_THERMOSTAT, CONF_HYSTERESIS)
    }


class MoesRelayHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create a zone."""
        if user_input is not None:
            thermostat = user_input[CONF_THERMOSTAT]
            await self.async_set_unique_id(thermostat)
            self._abort_if_unique_id_configured()

            title = user_input[CONF_ZONE_NAME].strip() or thermostat
            return self.async_create_entry(title=title, data=_supported_data(user_input))

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MoesRelayHeatingOptionsFlow(config_entry)


class MoesRelayHeatingOptionsFlow(config_entries.OptionsFlow):
    """Edit existing zone."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Edit zone options."""
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=_supported_data(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(current),
        )
