from datetime import datetime, timedelta
import logging
from typing import Dict, List, Tuple, Union
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from homeassistant.core import HomeAssistant

from . import const, dal
from .config import Configuration

_LOGGER = logging.getLogger(__name__)

CONSUMPTION_MODEL_PREFIX = "consumption_model"
QUANTILE_MODELS = {
    "min": {"alpha": 0.05, "suffix": "_low.pkl"},
    "med": {"alpha": 0.50, "suffix": "_med.pkl"},
    "max": {"alpha": 0.95, "suffix": "_high.pkl"},
}
FEATURE_COLS = ["hour", "day_of_week"]


def train_consumption_model(df: pd.DataFrame):
    """Train quantile regression models for energy consumption prediction."""
    cfg = Configuration.get_instance()

    if df.empty or len(df) < 10:
        raise ValueError("Not enough data to train consumption model.")

    X = df[FEATURE_COLS].values
    y = df["power"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train models for each quantile
    models = {
        name: GradientBoostingRegressor(
            loss="quantile", alpha=params["alpha"], n_estimators=100, max_depth=3
        ).fit(X_scaled, y)
        for name, params in QUANTILE_MODELS.items()
    }

    # Save models and scaler
    for name, model in models.items():
        joblib.dump(
            model,
            cfg.storage_path(
                f"{CONSUMPTION_MODEL_PREFIX}{QUANTILE_MODELS[name]['suffix']}"
            ),
        )
    joblib.dump(scaler, cfg.storage_path(f"{CONSUMPTION_MODEL_PREFIX}_scaler.pkl"))


def load_consumption_models() -> (
    tuple[tuple[GradientBoostingRegressor, ...], StandardScaler]
):
    """Load trained models and scaler from disk."""
    cfg = Configuration.get_instance()

    models = {
        name: joblib.load(
            cfg.storage_path(f"{CONSUMPTION_MODEL_PREFIX}{params['suffix']}")
        )
        for name, params in QUANTILE_MODELS.items()
    }

    scaler = joblib.load(cfg.storage_path(f"{CONSUMPTION_MODEL_PREFIX}_scaler.pkl"))
    return tuple(models.values()), scaler


def predict_consumption(
    models: tuple[GradientBoostingRegressor, ...],
    scaler: StandardScaler,
    input_data: list[dict[str, int]],
) -> list[dict[str, int | float]]:
    """Predict energy consumption using quantile regression models."""
    df = pd.DataFrame(input_data)

    if not all(col in df.columns for col in FEATURE_COLS):
        raise ValueError(f"Input data must contain {FEATURE_COLS}")

    X = df[FEATURE_COLS].values
    X_scaled = scaler.transform(X)

    # Make predictions for each quantile
    predictions = df[["hour"]].copy()
    for model, name in zip(models, QUANTILE_MODELS.keys()):
        predictions[name] = model.predict(X_scaled)

    return predictions.to_dict("records")


async def collect_and_train(
    hass: HomeAssistant, start_time: datetime, end_time: datetime
) -> None:
    """Collect historical data and train the consumption models."""
    _LOGGER.info("Starting consumption data collection and training")

    # Collect and process data
    df = await dal.collect_consumption_data(hass, start_time, end_time)
    if df.empty:
        raise ValueError("No consumption data collected")

    # Train model in executor
    await hass.async_add_executor_job(train_consumption_model, df)
    _LOGGER.info("Consumption model training completed")


async def generate_predictions(
    hass: HomeAssistant, from_date: datetime, to_date: datetime, timezone: str
) -> list[dict[str, str | float]]:
    """Generate consumption predictions for the specified date range."""
    _LOGGER.info("Generating consumption predictions from %s to %s", from_date, to_date)
    tz = ZoneInfo(timezone)

    # Generate input data for each hour in the date range
    input_data = []
    current_date = from_date
    while current_date <= to_date:
        dt = datetime.combine(current_date, datetime.min.time(), tzinfo=tz)
        input_data.extend(
            [{"hour": hour, "day_of_week": dt.weekday()} for hour in range(24)]
        )
        current_date += timedelta(days=1)

    # Load models and make predictions
    models, scaler = await hass.async_add_executor_job(load_consumption_models)
    predictions = await hass.async_add_executor_job(
        predict_consumption, models, scaler, input_data
    )

    # Create timestamps for predictions
    timestamps = []
    current_date = from_date
    while current_date <= to_date:
        dt = datetime.combine(current_date, datetime.min.time(), tzinfo=tz)
        timestamps.extend(
            [(dt + timedelta(hours=hour)).isoformat() for hour in range(24)]
        )
        current_date += timedelta(days=1)

    # Combine timestamps with predictions
    predictions = [{"time": ts, **pred} for ts, pred in zip(timestamps, predictions)]
    hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION].update_forecast(predictions)
    _LOGGER.info(
        "Consumption predictions completed successfully with %d records",
        len(predictions),
    )
