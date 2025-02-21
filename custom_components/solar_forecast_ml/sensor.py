from abc import ABC, abstractmethod
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from numpy import mean

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const, config
from .forecast_coordinator import ForecastCoordinator
from .forecast_data import ForecastData

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


class ForecastSensorBase(CoordinatorEntity[ForecastCoordinator], SensorEntity, ABC):
    def __init__(
        self,
        coordinator: ForecastCoordinator,
        id: str,
        name: str,
    ):
        super().__init__(coordinator)
        self._state = None
        self._attributes = {}
        self._name = name
        self._id = id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def suggested_object_id(self):
        """Return the suggested object id."""
        return self._id

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return self._id

    @property
    def available(self):
        """Return True if the sensor is available."""
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._handle_update()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self):
        """Restore state when the entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_update()

    def _get_forecast(self, forecast_data_key: str):
        return self.coordinator.data[forecast_data_key]

    def _handle_update(self):
        forecast_data_key = self._get_forecast_data_key()
        forecasts = self.coordinator.data
        if forecast_data_key in forecasts:
            forecast_data = forecasts[forecast_data_key]
            self._state, self._attributes = self._get_state_and_attr_from_forecast(
                forecast_data
            )

    @abstractmethod
    def _get_forecast_data_key(self) -> str:
        """Get forecast data key."""

    @abstractmethod
    def _get_state_and_attr_from_forecast(
        self, forecast_data: ForecastData
    ) -> tuple[float, dict]:
        """Get state and attributes from forecast data."""


def get_forecast_records_for_rest_of_today(forecast_data: ForecastData):
    now = datetime.now(ZoneInfo(config.Configuration.get_instance().timezone))
    today = now.date()

    return (
        point[forecast_data.value_field_med]
        for point in forecast_data.forecast
        if (point_time := datetime.fromisoformat(point["time"])) > now
        and point_time.date() == today
    )


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
        return round(max(get_forecast_records_for_rest_of_today(forecast_data)), 1), {
            "forecast": forecast_data.forecast,
        }

    @property
    def unit_of_measurement(self):
        return "%"
