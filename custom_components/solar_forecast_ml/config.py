from pathlib import Path

from astral import LocationInfo

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import (
    CONF_POWER_CONSUMPTION_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_TIMEZONE,
    DOMAIN,
)


class Configuration:
    _instance = None

    def __init__(self):
        self.latitude = None
        self.longitude = None
        self.timezone = None
        self.pv_power_entity_id = None
        self.location = None
        self.power_consumption_entity_id = None
        self.storage_dir = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = Configuration()
        return cls._instance

    def set_config(self, config: dict, hass: HomeAssistant):
        """Set configuration values from the config entry."""
        self.latitude = config.get(CONF_LATITUDE)
        self.longitude = config.get(CONF_LONGITUDE)
        self.timezone = config.get(CONF_TIMEZONE)
        self.pv_power_entity_id = config.get(CONF_PV_POWER_ENTITY)
        self.power_consumption_entity_id = config.get(CONF_POWER_CONSUMPTION_ENTITY)
        self.location = LocationInfo(
            "Location", "Country", self.timezone, self.latitude, self.longitude
        )
        self.storage_dir = Path(hass.config.path(".storage", DOMAIN))

        if not self.storage_dir.exists():
            self.storage_dir.mkdir()

    def storage_path(self, file_name: str):
        return self.storage_dir.joinpath(file_name)
