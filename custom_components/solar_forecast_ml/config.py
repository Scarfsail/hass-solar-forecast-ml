from pathlib import Path

from astral import LocationInfo

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BATT_CAPACITY_ENTITY,
    CONF_BATT_MAX_SOC_ENTITY,
    CONF_BATT_MIN_SOC_ENTITY,
    CONF_BATT_MAX_ENERGY_ENTITY,
    CONF_POWER_CONSUMPTION_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_TIMEZONE,
    DOMAIN,
    CONF_BATT_MAX_POWER,
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
        self.pv_batt_capacity_entity_id = None
        self.pv_batt_max_energy_entity_id = None
        self.pv_batt_min_soc = None
        self.pv_batt_max_soc = None
        self.storage_dir = None
        self.pv_batt_max_power = None

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
        self.pv_batt_capacity_entity_id = config.get(CONF_BATT_CAPACITY_ENTITY)
        self.pv_batt_max_energy_entity_id = config.get(CONF_BATT_MAX_ENERGY_ENTITY)
        self.pv_batt_min_soc = config.get(CONF_BATT_MIN_SOC_ENTITY, 10)
        self.pv_batt_max_soc = config.get(CONF_BATT_MAX_SOC_ENTITY, 100)
        self.pv_batt_max_power = config.get(CONF_BATT_MAX_POWER, 3000)
        self.location = LocationInfo(
            "Location", "Country", self.timezone, self.latitude, self.longitude
        )
        self.storage_dir = Path(hass.config.path(".storage", DOMAIN))

        if not self.storage_dir.exists():
            self.storage_dir.mkdir()

    def storage_path(self, file_name: str):
        return self.storage_dir.joinpath(file_name)
