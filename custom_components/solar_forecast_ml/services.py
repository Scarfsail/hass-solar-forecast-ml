from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from . import (
    const,
    forecast_battery,
    forecast_consumption,
    forecast_grid,
    forecast_solar,
)
from .config import Configuration

_LOGGER = logging.getLogger(__name__)


def register_services(hass: HomeAssistant):
    """Register all forecast services."""
    hass.services.async_register(
        const.DOMAIN,
        "solar_train_from_history",
        solar_handle_train_from_history,
        schema=vol.Schema(
            {
                vol.Optional("days_back", default=60): cv.positive_int,
                vol.Optional("hours_offset", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        const.DOMAIN,
        "solar_predict",
        solar_handle_predict,
        schema=vol.Schema(
            {
                vol.Required("days_back"): cv.positive_int,
                vol.Required("days_forward"): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        const.DOMAIN,
        "consumption_train_from_history",
        consumption_handle_train_from_history,
        schema=vol.Schema(
            {
                vol.Optional("days_back", default=60): cv.positive_int,
                vol.Optional("hours_offset", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        const.DOMAIN,
        "consumption_predict",
        consumption_handle_predict,
        schema=vol.Schema(
            {
                vol.Required("days_back"): cv.positive_int,
                vol.Required("days_forward"): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        const.DOMAIN,
        "battery_predict",
        battery_handle_predict,
        schema=vol.Schema(
            {
                vol.Required("days_forward"): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        const.DOMAIN,
        "grid_predict",
        grid_handle_predict,
        schema=vol.Schema(
            {
                vol.Required("days_forward"): cv.positive_int,
            }
        ),
    )


async def solar_handle_train_from_history(call: ServiceCall):
    """Handle the solar forecast training service call."""
    hass = call.hass
    days_back = call.data.get("days_back", 60)
    hours_offset = call.data.get("hours_offset", 1)

    now = datetime.now()
    start_date = now - timedelta(days=days_back)
    end_date = now - timedelta(hours=hours_offset)

    try:
        await forecast_solar.collect_and_train(hass, start_date, end_date)
        _LOGGER.info("Solar training completed successfully")
    except Exception as e:
        _LOGGER.error("Error during solar training: %s", e)


async def solar_handle_predict(call: ServiceCall):
    """Handle the solar forecast prediction service call."""
    hass = call.hass
    cfg = Configuration.get_instance()

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    from_dt = now - timedelta(days=call.data.get("days_back", 0))
    to_dt = (
        now
        + timedelta(days=call.data.get("days_forward", 1) + 1)
        - timedelta(seconds=1)
    )

    tz = ZoneInfo(cfg.timezone)
    from_dt = from_dt.replace(tzinfo=tz)
    to_dt = to_dt.replace(tzinfo=tz)

    try:
        await forecast_solar.collect_and_predict(hass, from_dt, to_dt)

    except Exception as e:
        _LOGGER.error("Error during solar prediction: %s", e)


async def consumption_handle_train_from_history(call: ServiceCall):
    """Handle the consumption forecast training service call."""
    hass = call.hass
    days_back = call.data.get("days_back", 60)
    hours_offset = call.data.get("hours_offset", 1)

    now = datetime.now()
    start_time = now - timedelta(days=days_back)
    end_time = now - timedelta(hours=hours_offset)

    try:
        await forecast_consumption.collect_and_train(hass, start_time, end_time)
        _LOGGER.info("Consumption model trained successfully")
    except Exception as e:
        _LOGGER.error("Error training consumption model: %s", e)


async def consumption_handle_predict(call: ServiceCall):
    """Handle the consumption forecast prediction service call."""
    hass = call.hass
    config = Configuration.get_instance()

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    from_date = now - timedelta(days=call.data.get("days_back", 0))
    to_date = (
        now
        + timedelta(days=call.data.get("days_forward", 1) + 1)
        - timedelta(seconds=1)
    )

    try:
        await forecast_consumption.generate_predictions(
            hass, from_date, to_date, config.timezone
        )
    except Exception as e:
        _LOGGER.error("Error predicting consumption: %s", e)


async def battery_handle_predict(call: ServiceCall):
    """Handle battery capacity prediction service call."""
    hass = call.hass
    days = call.data.get("days_forward", 1)
    try:
        await hass.async_add_executor_job(
            forecast_battery.forecast_battery_capacity, hass, days
        )
    except Exception as e:
        _LOGGER.error("Error forecasting battery capacity: %s", e)


async def grid_handle_predict(call: ServiceCall):
    """Handle grid exchange prediction service call."""
    hass = call.hass
    days = call.data.get("days_forward", 1)
    try:
        await hass.async_add_executor_job(forecast_grid.forecast_grid, hass, days)
    except Exception as e:
        _LOGGER.error("Error forecasting grid exchange: %s", e)
