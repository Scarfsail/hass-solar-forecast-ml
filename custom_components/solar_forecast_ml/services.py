from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
import homeassistant.helpers.config_validation as cv

# Import model functions from model.py
from . import dal, model
from .const import DOMAIN  # Define DOMAIN in const.py

_LOGGER = logging.getLogger(__name__)

# Filenames for saving the model and scaler (saved in your config directory)
MODEL_PATH = "solar_power_model.pkl"
SCALER_PATH = "solar_scaler.pkl"


def register_services(hass: HomeAssistant):
    hass.services.async_register(
        DOMAIN,
        "train",
        handle_train_service,
        schema=vol.Schema(
            {
                vol.Optional("days_back", default=60): cv.positive_int,
                vol.Optional("hours_offset", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "train_from_csv",
        handle_train_from_csv_service,
        schema=vol.Schema(
            {vol.Required("csv_file", default="pv_power.csv"): cv.string}
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "predict",
        handle_predict_service,
        schema=vol.Schema(
            {
                vol.Required("from"): cv.datetime,
                vol.Required("to"): cv.datetime,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


async def handle_train_service(call: ServiceCall):
    """Handle the solar forecast training service call."""
    hass = call.hass
    _LOGGER.info("Collecting training data ...")

    # Retrieve sensor data for the same period
    days_back = call.data.get("days_back", 60)
    hours_offset = call.data.get("hours_offset", 1)

    now = datetime.now()
    sensor_start = now - timedelta(days=days_back)
    sensor_end = now - timedelta(hours=hours_offset)
    _LOGGER.info(
        "Collecting sensor training data from %s to %s", sensor_start, sensor_end
    )

    sensor_records = await hass.async_add_executor_job(
        dal.collect_sensor_data, hass, sensor_start, sensor_end
    )
    _LOGGER.info("Collected %d sensor records", len(sensor_records))
    await train_model(hass, sensor_records)


async def handle_train_from_csv_service(call: ServiceCall):
    """Handle the solar forecast training service call."""
    hass = call.hass
    _LOGGER.info("Collecting training data ...")

    # Retrieve sensor data for the same period
    csv_file_name = hass.config.path(call.data.get("csv_file"))

    _LOGGER.info("Collecting sensor training data from CSV %s ", csv_file_name)

    sensor_records = await hass.async_add_executor_job(
        dal.collect_sensor_csv_data, csv_file_name
    )
    _LOGGER.info("Collected %d sensor records", len(sensor_records))
    await train_model(hass, sensor_records)


async def train_model(hass: HomeAssistant, sensor_records: list[dal.SensorDataRecord]):
    times = [entry["time"] for entry in sensor_records]

    # Compute the min and max timestamps
    start_date = min(times)
    end_date = max(times)

    _LOGGER.info("Collecting meteo training data from %s to %s", start_date, end_date)
    # Collect historical meteo data (runs in executor as it is blocking)
    meteo_records = await hass.async_add_executor_job(
        dal.collect_meteo_data, start_date, end_date, False
    )
    _LOGGER.info("Collected %d meteo records", len(meteo_records))

    if not meteo_records or not sensor_records:
        _LOGGER.error("Not enough data collected for training.")
        return

    try:
        data_df = dal.merge_data(meteo_records, sensor_records)
    except Exception as e:
        _LOGGER.error("Error merging data: %s", e)
        return

    _LOGGER.info("Merged data contains %d records", len(data_df))
    if len(data_df) < 10:
        _LOGGER.error("Not enough merged data for training.")
        return

    def train():
        return model.train_model(
            data_df, hass.config.path(MODEL_PATH), hass.config.path(SCALER_PATH)
        )

    # Save training data to CSV with current timestamp
    csv_filename = "solar_training_data.csv"
    data_df.to_csv(hass.config.path(csv_filename), index=False)
    _LOGGER.info("Training data saved to %s", csv_filename)
    try:
        await hass.async_add_executor_job(train)
        _LOGGER.info(
            "Training completed. Model saved at %s", hass.config.path(MODEL_PATH)
        )
    except Exception as e:
        _LOGGER.error("Error during training: %s", e)


async def handle_predict_service(call: ServiceCall):
    """Handle the solar forecast prediction service call."""
    hass = call.hass
    from_dt = call.data.get("from")
    to_dt = call.data.get("to")

    _LOGGER.info("Predicting power from %s to %s", from_dt, to_dt)
    if not from_dt or not to_dt:
        _LOGGER.error("Missing 'from' or 'to' in forecast service call.")
        return

    # If the provided datetimes are naive, assign the Europe/Prague timezone.
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=ZoneInfo("Europe/Prague"))
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=ZoneInfo("Europe/Prague"))

    try:
        # Gather forecast meteo data (hourly then interpolated to 15-min intervals)
        def get_forecast():
            # return model.collect_forecast_meteo_data(from_dt, to_dt)
            return dal.collect_meteo_data(from_dt, to_dt, True)

        forecast_data = await hass.async_add_executor_job(get_forecast)
        _LOGGER.info("Collected %d forecast meteo records", len(forecast_data))

        # Load the trained model and scaler
        def load():
            return model.load_model_and_scaler(
                hass.config.path(MODEL_PATH), hass.config.path(SCALER_PATH)
            )

        model_obj, scaler = await hass.async_add_executor_job(load)

        # Run predictions for each 15-minute record
        def predict():
            return model.predict_power(model_obj, scaler, forecast_data)

        predictions = await hass.async_add_executor_job(predict)
        _LOGGER.info("Prediction done with %s predictions", len(predictions))

        # Combine each timestamp with its predicted power
        result = []
        for rec, pred in zip(forecast_data, predictions):
            time_val = rec["time"]
            time_str = (
                time_val.isoformat()
                if hasattr(time_val, "isoformat")
                else str(time_val)
            )
            result.append({"time": time_str, "predicted_power": pred})
        # Update a sensor with the latest prediction and attach full prediction details as attributes
        hass.states.async_set(
            "sensor.solar_panel_forecast",
            predictions[-1] if predictions else 0,
            {"predictions": result},
        )

        return {"predictions": result}
    except Exception as e:
        _LOGGER.error("Error during prediction: %s", e)
