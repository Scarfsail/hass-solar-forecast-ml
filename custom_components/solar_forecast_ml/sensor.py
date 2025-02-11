from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.sensor import SensorEntity
from . import const

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Solar Forecast ML sensor platform."""
    _LOGGER.debug("Setting up Solar Forecast ML sensor platform")
    pv_power_forecast = ForecastSensor("solar_panels_forecast", "Solar Panels Forecast")
    power_consumption_forecast = ForecastSensor(
        "power_consumption_forecast", "Power Consumption Forecast"
    )
    hass.data.setdefault(const.DOMAIN, {})[const.SENSOR_PV_POWER_FORECAST] = (
        pv_power_forecast
    )
    hass.data.setdefault(const.DOMAIN, {})[const.SENSOR_POWER_CONSUMPTION] = (
        power_consumption_forecast
    )

    async_add_entities([pv_power_forecast, power_consumption_forecast])

    return True


class ForecastSensor(SensorEntity, RestoreEntity):
    """Representation of a solar panel forecast sensor."""

    def __init__(self, id: str, name: str):
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
        self._state = datetime.now()
        self._attributes = {"forecast": forecast}
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Restore state when the entity is added to hass."""
        await super().async_added_to_hass()
        # Retrieve the previous state

        old_state = await self.async_get_last_state()
        if old_state is not None:
            self._attributes = old_state.attributes
            self._state = old_state.state
