from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.core import ServiceCall

from . import const, forecast_solar
from .config import Configuration

_LOGGER = logging.getLogger(__name__)


async def handle_train_from_history_service(call: ServiceCall):
    """Handle the solar forecast training service call."""
    hass = call.hass
    days_back = call.data.get("days_back", 60)
    hours_offset = call.data.get("hours_offset", 1)

    now = datetime.now()
    start_date = now - timedelta(days=days_back)
    end_date = now - timedelta(hours=hours_offset)

    try:
        await forecast_solar.collect_and_train(hass, start_date, end_date)
        _LOGGER.info("Training completed successfully")
    except Exception as e:
        _LOGGER.error("Error during training: %s", e)


async def handle_predict_service(call: ServiceCall):
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

    # Ensure dates are timezone-aware
    tz = ZoneInfo(cfg.timezone)
    from_dt = from_dt.replace(tzinfo=tz)
    to_dt = to_dt.replace(tzinfo=tz)

    try:
        await forecast_solar.collect_and_predict(hass, from_dt, to_dt)
    except Exception as e:
        _LOGGER.error("Error during prediction: %s", e)
