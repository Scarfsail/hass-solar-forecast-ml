# services.py
from datetime import datetime, timedelta
import logging

from homeassistant.core import ServiceCall

from . import const, forecast_consumption
from .config import Configuration

_LOGGER = logging.getLogger(__name__)


async def handle_train_from_history_service(call: ServiceCall):
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


async def handle_predict_service(call: ServiceCall):
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
