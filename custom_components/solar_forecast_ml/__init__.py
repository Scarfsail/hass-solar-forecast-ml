import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import dal
from .config import Configuration
from .const import DOMAIN
from .services import register_services

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == "1.0.0":
        # Already up to date
        return True

    # If migration fails, we'll remove the config entry
    return False


# If your integration supports config entries, you need to define async_setup_entry.
async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up the solar_forecast_ml integration."""

    # Save config entry data if needed.
    config = {**entry.data, **entry.options}
    hass.data.setdefault(DOMAIN, {})["config"] = config

    Configuration.get_instance().set_config(config, hass)
    register_services(hass)

    # Forward setup for the sensor platform
    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["sensor"],
    )
    _LOGGER.info("Solar Forecast ML integration has been set up")
    return True


# Optionally, define async_unload_entry if you want to support unloading config entries.
async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    # Remove any services or clean up resources if needed.
    return True
