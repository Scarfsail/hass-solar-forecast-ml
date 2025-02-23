import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const
from .forecast_coordinator import ForecastCoordinator
from .forecast_data import ForecastData
from .forecast_sensor_base import ForecastSensorBase

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Solar Forecast ML sensor platform."""
    _LOGGER.debug("Setting up Solar Forecast ML sensor platform")
    coordinator: ForecastCoordinator = hass.data[const.DOMAIN][const.COORDINATOR]

    forecast_sensors = [
        ForecastSensorSolarPower(
            coordinator,
            "pv_solar_panels_power_forecast",
            "Solar Panels Power Forecast",
        ),
        ForecastSensorPowerConsumption(
            coordinator,
            "pv_power_consumption_forecast",
            "Power Consumption Forecast",
        ),
        ForecastSensorBattery(
            coordinator,
            "pv_battery_capacity_forecast",
            "Battery Capacity Forecast",
        ),
        ForecastSensorGridPower(
            coordinator,
            "pv_grid_power_forecast",
            "Grid export / import power Forecast",
        ),
        ForecastSensorSolarEnergyToday(
            coordinator,
            "pv_solar_panels_energy_forecast_today",
            "Solar Panels Energy Forecast (Today)",
        ),
        ForecastSensorSolarEnergyRestOfToday(
            coordinator,
            "pv_solar_panels_forecast_energy_rest_of_today",
            "Solar Panels energy Forecast (Rest of Today)",
        ),
        ForecastSensorGridEnergyRestOfToday(
            coordinator,
            "pv_grid_energy_forecast_rest_of_today",
            "Grid export / import energy Forecast (Rest of Today)",
        ),
    ]

    async_add_entities(forecast_sensors)

    return True


class ForecastSensorSolarPower(ForecastSensorBase):
    def _get_forecast_data_key(self) -> str:
        return const.FORECAST_DATA_PV_POWER

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(forecast_data.get_nearest_forecast_record()), {
            "forecast": forecast_data.forecast
        }

    @property
    def unit_of_measurement(self):
        return "W"


class ForecastSensorPowerConsumption(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_POWER_CONSUMPTION

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(forecast_data.get_nearest_forecast_record()), {
            "forecast": forecast_data.forecast
        }

    @property
    def unit_of_measurement(self):
        return "W"


class ForecastSensorBattery(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_BATTERY

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(forecast_data.get_nearest_forecast_record()), {
            "forecast": forecast_data.forecast,
        }

    @property
    def unit_of_measurement(self):
        return "%"


class ForecastSensorGridPower(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_GRID

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(forecast_data.get_nearest_forecast_record()), {
            "forecast": forecast_data.forecast
        }

    @property
    def unit_of_measurement(self):
        return "W"


class ForecastSensorSolarEnergyToday(ForecastSensorBase):
    def _get_forecast_data_key(self) -> str:
        return const.FORECAST_DATA_PV_POWER

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(sum(forecast_data.get_forecast_records_for_today()) / 4), {
            "forecast": forecast_data.aggregate_by_interval("sum", lambda x: x / 4)
        }

    @property
    def unit_of_measurement(self):
        return "Wh"


class ForecastSensorSolarEnergyRestOfToday(ForecastSensorBase):
    def _get_forecast_data_key(self) -> str:
        return const.FORECAST_DATA_PV_POWER

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(
            sum(forecast_data.get_forecast_records_for_rest_of_today()) / 4
        ), {}

    @property
    def unit_of_measurement(self):
        return "Wh"


class ForecastSensorGridEnergyRestOfToday(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_GRID

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(sum(forecast_data.get_forecast_records_for_rest_of_today())), {}

    @property
    def unit_of_measurement(self):
        return "Wh"
