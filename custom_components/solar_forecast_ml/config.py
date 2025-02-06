from astral import LocationInfo
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE

from .const import CONF_PV_POWER_ENTITY, CONF_TIMEZONE


class Configuration:
    _instance = None

    def __init__(self):
        self.latitude = None
        self.longitude = None
        self.timezone = None
        self.pv_power_entity_id = None
        self.location = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = Configuration()
        return cls._instance

    def set_config(self, config: dict):
        """Set configuration values from the config entry."""
        self.latitude = config.get(CONF_LATITUDE)
        self.longitude = config.get(CONF_LONGITUDE)
        self.timezone = config.get(CONF_TIMEZONE)
        self.pv_power_entity_id = config.get(CONF_PV_POWER_ENTITY)
        self.location = LocationInfo(
            "Location", "Country", self.timezone, self.latitude, self.longitude
        )
