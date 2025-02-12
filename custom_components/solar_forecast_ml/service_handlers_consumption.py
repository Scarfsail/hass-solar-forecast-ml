# services.py
from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.core import ServiceCall

from . import dal, forecast_consumption, const
from .config import Configuration

_LOGGER = logging.getLogger(__name__)

# Schemas for the new consumption services


async def handle_train_from_history_service(call: ServiceCall):
    """Service handler to train the consumption prediction model."""
    hass = call.hass
    days_back = call.data.get("days_back", 60)
    hours_offset = call.data.get("hours_offset", 1)
    now = datetime.now()
    start_time = now - timedelta(days=days_back)
    end_time = now - timedelta(hours=hours_offset)

    try:

        def train():
            df = dal.collect_consumption_data(hass, start_time, end_time)
            return forecast_consumption.train_consumption_model(df)

        await hass.async_add_executor_job(train)
        _LOGGER.info("Consumption model trained successfully.")
        # Optionally, update an entity state to indicate training is complete.
        hass.states.async_set(
            "sensor.house_consumption_prediction", 0, {"status": "trained"}
        )
    except Exception as e:
        _LOGGER.error("Error training consumption model: %s", e)


async def handle_train_from_csv_service(call: ServiceCall):
    pass


async def handle_predict_service(call: ServiceCall):
    """Service handler to predict energy consumption for a given date range."""
    hass = call.hass
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    from_date = now - timedelta(days=call.data.get("days_back", 0))
    to_date = (
        now
        + timedelta(days=call.data.get("days_forward", 1) + 1)
        - timedelta(seconds=1)
    )

    days_diff = (to_date - from_date).days + 1
    if days_diff < 1:
        _LOGGER.error("Invalid date range")
        return

    try:
        config = Configuration.get_instance()
        tz = ZoneInfo(config.timezone) if config.timezone else ZoneInfo("Europe/Prague")

        # Generate input data for each hour in the date range
        input_data = []
        current_date = from_date
        while current_date <= to_date:
            dt = datetime.combine(current_date, datetime.min.time(), tzinfo=tz)
            input_data.extend(
                [
                    {"hour": hour, "day_of_week": dt.weekday()}  # Monday=0, Sunday=6
                    for hour in range(24)
                ]
            )
            current_date += timedelta(days=1)

        def predict():
            models, scaler = forecast_consumption.load_consumption_models()
            return forecast_consumption.predict_consumption(models, scaler, input_data)

        predictions = await hass.async_add_executor_job(predict)
        _LOGGER.info("Generated %d hourly predictions", len(predictions))

        # Create a list of timestamps for each prediction
        timestamps = []
        current_date = from_date
        while current_date <= to_date:
            dt = datetime.combine(current_date, datetime.min.time(), tzinfo=tz)
            timestamps.extend(
                [(dt + timedelta(hours=hour)).isoformat() for hour in range(24)]
            )
            current_date += timedelta(days=1)

        # Combine timestamps with predictions
        predictions_with_time = [
            {"time": ts, **pred} for ts, pred in zip(timestamps, predictions)
        ]
        hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION].update_forecast(
            predictions_with_time
        )

    except Exception as e:
        _LOGGER.error("Error predicting consumption: %s", e)
