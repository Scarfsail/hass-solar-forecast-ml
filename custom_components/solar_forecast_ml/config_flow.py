import pytz
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.helpers import selector

from .const import (
    CONF_POWER_CONSUMPTION_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_TIMEZONE,
    DOMAIN,
)


def get_schema(defaults=None):
    """Get schema with optional defaults."""
    if defaults is None:
        defaults = {}

    return vol.Schema(
        {
            vol.Required(
                CONF_LATITUDE, default=defaults.get(CONF_LATITUDE, 50.08804)
            ): str,
            vol.Required(
                CONF_LONGITUDE, default=defaults.get(CONF_LONGITUDE, 14.42076)
            ): str,
            vol.Required(
                CONF_TIMEZONE, default=defaults.get(CONF_TIMEZONE, "Europe/Prague")
            ): str,
            vol.Required(
                CONF_PV_POWER_ENTITY, default=defaults.get(CONF_PV_POWER_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_POWER_CONSUMPTION_ENTITY,
                default=defaults.get(CONF_POWER_CONSUMPTION_ENTITY),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


class SolarForecastMLConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            try:
                pytz.timezone(user_input[CONF_TIMEZONE])
                return self.async_create_entry(
                    title="Solar Forecast ML", data=user_input
                )
            except pytz.exceptions.UnknownTimeZoneError:
                errors[CONF_TIMEZONE] = "invalid_timezone"

        return self.async_show_form(
            step_id="user",
            data_schema=get_schema(),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            try:
                pytz.timezone(user_input[CONF_TIMEZONE])

                # Use config_entry.options instead of config_entry.data for defaults
                return self.async_create_entry(
                    title="",
                    # Merge existing options with new user input
                    data=self.config_entry.options | user_input,
                )
            except pytz.exceptions.UnknownTimeZoneError:
                errors[CONF_TIMEZONE] = "invalid_timezone"

        return self.async_show_form(
            step_id="init",
            # Use config_entry.options instead of config_entry.data for defaults
            data_schema=get_schema(
                {**self.config_entry.data, **self.config_entry.options}
            ),
            errors=errors,
        )
