from datetime import datetime
import logging
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from homeassistant.core import HomeAssistant

from . import const, dal
from .config import Configuration
from .dal import METEO_PARAMS

_LOGGER = logging.getLogger(__name__)


# Update feature_cols to use the same parameter names
feature_cols = METEO_PARAMS  # + ["sun_altitude", "sun_azimuth"]


def when_model_was_trained() -> datetime:
    """Return the timestamp when the solar power model was trained."""
    cfg = Configuration.get_instance()
    model_path = cfg.storage_path("solar_power_model.pkl")
    if not model_path.exists():
        return None
    return datetime.fromtimestamp(model_path.stat().st_mtime, tz=ZoneInfo(cfg.timezone))


def is_model_trained() -> bool:
    """Check if the solar power model is trained."""
    cfg = Configuration.get_instance()
    return cfg.storage_path("solar_power_model.pkl").exists()


async def collect_and_train(
    hass: HomeAssistant, start_date: datetime, end_date: datetime
) -> None:
    """Collect historical data and train the model."""
    _LOGGER.info("Starting solar data collection and training")
    cfg = Configuration.get_instance()

    # Collect sensor data
    sensor_records = await dal.collect_pv_power_historical_data(
        hass, start_date, end_date
    )
    if not sensor_records:
        raise ValueError("No sensor data collected")

    # Collect meteo data
    meteo_records = await hass.async_add_executor_job(
        dal.collect_meteo_data, start_date, end_date, False
    )
    if not meteo_records:
        raise ValueError("No meteo data collected")

    # Merge data - note the added hass parameter
    data_df = await dal.merge_meteo_and_pv_power_data(
        hass, meteo_records, sensor_records
    )
    if len(data_df) < 10:
        raise ValueError("Not enough merged data for training")

    # Save training data
    csv_filename = cfg.storage_path("solar_training_data.csv")
    await hass.async_add_executor_job(
        lambda: data_df.to_csv(path_or_buf=csv_filename, index=False)
    )

    # Train model
    await hass.async_add_executor_job(
        train_model,
        data_df,
        cfg.storage_path("solar_power_model.pkl"),
        cfg.storage_path("solar_scaler.pkl"),
    )
    _LOGGER.info("Solar power model training completed")


async def collect_and_predict(
    hass: HomeAssistant, from_date: datetime, to_date: datetime
):
    """Collect forecast data and make predictions."""
    _LOGGER.info("Forecasting power consumption from %s to %s", from_date, to_date)
    cfg = Configuration.get_instance()

    # Get forecast data
    forecast_data = await hass.async_add_executor_job(
        dal.collect_meteo_data, from_date, to_date, True
    )
    if not forecast_data:
        raise ValueError("No forecast data collected")

    # Load model and make predictions
    model, scaler = await hass.async_add_executor_job(
        load_model_and_scaler,
        cfg.storage_path("solar_power_model.pkl"),
        cfg.storage_path("solar_scaler.pkl"),
    )

    predictions = predict_power(model, scaler, forecast_data)

    # Format results
    result = [
        {
            "time": rec["time"].isoformat()
            if hasattr(rec["time"], "isoformat")
            else str(rec["time"]),
            "power": pred,
        }
        for rec, pred in zip(forecast_data, predictions)
    ]

    hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST].update_forecast(result)
    _LOGGER.info(
        "Power consumption forecast completed successfully with %d records", len(result)
    )


def train_model(data_df, model_path, scaler_path):
    """Train an MLP neural network regressor using the merged data.
    The data_df must include all meteo features and a 'power' column.
    Saves the trained model and scaler to the provided paths.
    """

    _LOGGER.info("Starting training with %d records", len(data_df))

    for col in [*feature_cols, "power"]:
        if col not in data_df.columns:
            raise ValueError(f"Column {col} not found in data.")
    X = data_df[feature_cols].values
    y = data_df["power"].values

    # Scale the features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Create and train the MLP regressor
    model = MLPRegressor(
        random_state=42,  # for reproducibility
        hidden_layer_sizes=(128, 64),
        activation="relu",
        learning_rate="adaptive",
        solver="adam",
        max_iter=5000,
    )

    # Perform 5-fold cross validation
    # cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="r2")
    # _LOGGER.info(f"Cross-validation R² scores: {cv_scores}")
    # _LOGGER.info(
    #    f"Mean R² score: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})"
    # )

    model.fit(X_scaled, y)

    # Save the model and scaler
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    return model, scaler


def load_model_and_scaler(model_path, scaler_path):
    """Load the trained model and scaler."""
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    return model, scaler


def predict_power(model, scaler, forecast_data):
    """
    Given forecast_data (a list of dictionaries with meteo features), predict panel power.
    Returns a list of predictions.
    """

    df = pd.DataFrame(forecast_data)
    for col in feature_cols:
        if col not in df.columns:
            raise ValueError(f"Forecast data missing column {col}")
    X = df[feature_cols].values
    X_scaled = scaler.transform(X)
    predictions = model.predict(X_scaled)
    return predictions.flatten().tolist()
