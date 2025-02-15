import logging

from homeassistant.core import ServiceCall

from .forecast_grid import forecast_grid

_LOGGER = logging.getLogger(__name__)


async def handle_grid_forecast_service(call: ServiceCall):
    hass = call.hass
    days = call.data.get("days_forward", 1)
    try:
        await hass.async_add_executor_job(forecast_grid, hass, days)
    except Exception as e:
        _LOGGER.error("Error forecasting grid exchange: %s", e)
