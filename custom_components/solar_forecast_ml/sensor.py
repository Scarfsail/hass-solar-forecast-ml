from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Configuration, const
from .forecast_coordinator import ForecastCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Solar Forecast ML sensor platform."""
    _LOGGER.debug("Setting up Solar Forecast ML sensor platform")
    coordinator: ForecastCoordinator = hass.data[const.DOMAIN][const.COORDINATOR]

    forecast_sensors = [
        ForecastSensor(
            coordinator, const.SENSOR_PV_POWER_FORECAST, "Solar Panels Forecast"
        ),
        ForecastSensor(
            coordinator, const.SENSOR_PV_POWER_CONSUMPTION, "Power Consumption Forecast"
        ),
        ForecastSensor(
            coordinator, const.SENSOR_PV_BATTERY_FORECAST, "Battery Capacity Forecast"
        ),
        ForecastSensor(
            coordinator, const.SENSOR_PV_GRID_FORECAST, "Grid export / import Forecast"
        ),
    ]

    async_add_entities(forecast_sensors)

    return True


class ForecastSensor(CoordinatorEntity[ForecastCoordinator], SensorEntity):
    """Representation of a solar panel forecast sensor."""

    def __init__(self, coordinator: ForecastCoordinator, id: str, name: str):
        super().__init__(coordinator)
        self._state = None
        self._attributes = {"forecast": []}
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

    def update_forecast(self, forecast):
        """Update the sensor state and attributes.

        :param state: The current forecast value (e.g. next interval's prediction)
        :param forecast: A list of forecast values (e.g. a timeline of predictions)
        """
        config = Configuration.get_instance()
        self._state = datetime.now(ZoneInfo(config.timezone))
        self._attributes = {"forecast": forecast}
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._handle_update()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self):
        """Restore state when the entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_update()

    def _handle_update(self):
        forecasts = self.coordinator.data
        if self._id in forecasts:
            forecast_data = forecasts[self._id]
            self._state = 0
            self._attributes = {"forecast": forecast_data.forecast}
