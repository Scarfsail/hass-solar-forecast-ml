from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import config, const
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
        ForecastSensorSolar(
            coordinator,
            "pv_solar_power_forecast",
            "Solar Panels Forecast",
        ),
        ForecastSensorSolarNow(
            coordinator,
            "pv_solar_power_forecast_now",
            "Solar Panels Forecast Now",
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
        ForecastSensorGrid(
            coordinator,
            "pv_grid_forecast",
            "Grid export / import Forecast",
        ),
    ]

    async_add_entities(forecast_sensors)

    return True


def get_forecast_records_for_rest_of_today(forecast_data: ForecastData):
    now = datetime.now(ZoneInfo(config.Configuration.get_instance().timezone))
    today = now.date()

    return (
        point[forecast_data.value_field_med]
        for point in forecast_data.forecast
        if (point_time := datetime.fromisoformat(point["time"])) > now
        and point_time.date() == today
    )


def get_nearest_forecast_record(forecast_data: ForecastData) -> float | None:
    now = datetime.now(ZoneInfo(config.Configuration.get_instance().timezone))

    for point in forecast_data.forecast:
        point_time = datetime.fromisoformat(point["time"])
        if point_time >= now:
            return point[forecast_data.value_field_med]

    return None


class ForecastSensorSolar(ForecastSensorBase):
    def _get_forecast_data_key(self) -> str:
        return const.FORECAST_DATA_PV_POWER

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(sum(get_forecast_records_for_rest_of_today(forecast_data)) / 4), {
            "forecast": forecast_data.forecast
        }

    @property
    def unit_of_measurement(self):
        return "Wh"


class ForecastSensorPowerConsumption(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_POWER_CONSUMPTION

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(sum(get_forecast_records_for_rest_of_today(forecast_data))), {
            "forecast": forecast_data.forecast
        }

    @property
    def unit_of_measurement(self):
        return "Wh"


class ForecastSensorGrid(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_GRID

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(sum(get_forecast_records_for_rest_of_today(forecast_data))), {
            "forecast": forecast_data.forecast
        }

    @property
    def unit_of_measurement(self):
        return "Wh"


class ForecastSensorBattery(ForecastSensorBase):
    def _get_forecast_data_key(self):
        return const.FORECAST_DATA_BATTERY

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(max(get_forecast_records_for_rest_of_today(forecast_data))), {
            "forecast": forecast_data.forecast,
        }

    @property
    def unit_of_measurement(self):
        return "%"


class ForecastSensorSolarNow(ForecastSensorBase):
    def _get_forecast_data_key(self) -> str:
        return const.FORECAST_DATA_PV_POWER

    def _get_state_and_attr_from_forecast(self, forecast_data: ForecastData):
        return round(get_nearest_forecast_record(forecast_data)), {}

    @property
    def unit_of_measurement(self):
        return "W"
