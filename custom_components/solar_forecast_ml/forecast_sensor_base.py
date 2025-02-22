from abc import ABC, abstractmethod
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .forecast_coordinator import ForecastCoordinator
from .forecast_data import ForecastData

_LOGGER = logging.getLogger(__name__)


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
