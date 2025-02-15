import logging

from homeassistant.core import ServiceCall

from .forecast_battery import forecast_battery_capacity

_LOGGER = logging.getLogger(__name__)


async def handle_battery_forecast_service(call: ServiceCall):
    hass = call.hass
    # Assume 'days' is passed as data (e.g., number of days to forecast)
    days = call.data.get("days_forward", 1)
    try:
        # Run the simulation in an executor since it might be blocking.
        await hass.async_add_executor_job(forecast_battery_capacity, hass, days)

    except Exception as e:
        _LOGGER.error("Error forecasting battery capacity: %s", e)
