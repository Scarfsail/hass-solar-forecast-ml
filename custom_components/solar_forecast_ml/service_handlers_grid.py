import logging

from homeassistant.core import ServiceCall

from . import const
from .forecast_grid import forecast_grid

_LOGGER = logging.getLogger(__name__)


async def handle_grid_forecast_service(call: ServiceCall):
    hass = call.hass
    days = call.data.get("days_forward", 1)
    try:
        forecast = await hass.async_add_executor_job(forecast_grid, hass, days)
        # Update the sensor that stores grid forecast. For example:
        grid_sensor = hass.data[const.DOMAIN][const.SENSOR_GRID_FORECAST]
        grid_sensor.update_forecast(forecast)
    except Exception as e:
        _LOGGER.error("Error forecasting grid exchange: %s", e)
