import datetime
import logging
from typing import TypedDict
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun
import joblib
import pandas as pd
import requests
from sklearn.model_selection import GridSearchCV, cross_val_score
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from homeassistant.components.recorder import history
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE

from .const import CONF_PV_POWER_ENTITY, CONF_TIMEZONE

_LOGGER = logging.getLogger(__name__)

# Define your location parameters (adjust as needed)
# Remove hardcoded values and define globals
LATITUDE = None
LONGITUDE = None
TIMEZONE = None
LOCATION = None
PV_POWER_ENTITY_ID = None


def set_config(config: dict):
    """Set configuration values from the config entry."""
    global LATITUDE, LONGITUDE, TIMEZONE, LOCATION, PV_POWER_ENTITY_ID
    LATITUDE = config.get(CONF_LATITUDE)
    LONGITUDE = config.get(CONF_LONGITUDE)
    TIMEZONE = config.get(CONF_TIMEZONE)
    PV_POWER_ENTITY_ID = config.get(CONF_PV_POWER_ENTITY)
    LOCATION = LocationInfo("Location", "Country", TIMEZONE, LATITUDE, LONGITUDE)


class SensorDataRecord(TypedDict):
    time: pd.Timestamp
    power: float


def is_daytime(dt: datetime):
    """Return True if dt is between sunrise and sunset."""
    s = sun(LOCATION.observer, date=dt.date(), tzinfo=dt.tzinfo)
    dawn = s["dawn"] - datetime.timedelta(hours=1)
    dusk = s["dusk"] + datetime.timedelta(hours=1)
    return dawn <= dt <= dusk


def get_sun_position(dt: datetime):
    """Return sun altitude and azimuth for a given datetime.
    Uses pysolar if available; otherwise returns 0.0 for both.
    """

    try:
        from pysolar.solar import get_altitude, get_azimuth

        altitude = get_altitude(LATITUDE, LONGITUDE, dt)
        azimuth = get_azimuth(LATITUDE, LONGITUDE, dt)
    except ImportError:
        _LOGGER.warning("pysolar not installed, sun position set to 0.0")
        altitude = 0.0
        azimuth = 0.0
    return altitude, azimuth


def collect_meteo_data(from_date, to_date, skip_night=True):
    """
    Collect historical meteo data from the Open-Meteo API between from_date and to_date.
    The dates must be datetime.date objects.
    Returns a list of dictionaries (one per hour, daytime only).
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&hourly=temperature_2m,relativehumidity_2m,rain,showers,snowfall,cloudcover,"
        "cloudcover_low,cloudcover_mid,cloudcover_high,visibility,shortwave_radiation,"
        "direct_radiation,diffuse_radiation,direct_normal_irradiance,terrestrial_radiation"
        f"&start_date={from_date:%Y-%m-%d}&end_date={to_date:%Y-%m-%d}&timezone=Europe%2FBerlin"
    )
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    hourly = data.get("hourly", {})
    records = []
    times = hourly.get("time", [])
    for i, time in enumerate(times):
        try:
            dt = pd.to_datetime(time)
            # Ensure dt is timezone-aware.

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Europe/Prague"))

            # Only include daytime records
            if not is_daytime(dt) and skip_night:
                continue

            altitude, azimuth = get_sun_position(dt)
            record = {
                "time": dt,
                "temperature": float(hourly["temperature_2m"][i]),
                "humidity": float(hourly["relativehumidity_2m"][i]),
                "rain": float(hourly["rain"][i]),
                "showers": float(hourly["showers"][i]),
                "snowfall": float(hourly["snowfall"][i]),
                "cloudcover": float(hourly["cloudcover"][i]),
                "cloudcover_low": float(hourly["cloudcover_low"][i]),
                "cloudcover_mid": float(hourly["cloudcover_mid"][i]),
                "cloudcover_high": float(hourly["cloudcover_high"][i]),
                "visibility": float(hourly["visibility"][i]),
                "shortwave_radiation": float(hourly["shortwave_radiation"][i]),
                "direct_radiation": float(hourly["direct_radiation"][i]),
                "diffuse_radiation": float(hourly["diffuse_radiation"][i]),
                "direct_normal_radiation": float(hourly["direct_normal_irradiance"][i]),
                "terrestrial_radiation": float(hourly["terrestrial_radiation"][i]),
                "sun_altitude": altitude,
                "sun_azimuth": azimuth,
            }
            records.append(record)
        except Exception as e:
            _LOGGER.error(f"Error processing meteo record index {i}: {e}")
    return records


def collect_sensor_data(hass, start_time, end_time) -> list[SensorDataRecord]:
    """
    Collect historical sensor data from Home Assistant for the given entity.
    Returns a list of dictionaries with keys 'time' and 'power'.
    Uses the recorder's history API and fills gaps with zero power values.
    """

    entity_id = PV_POWER_ENTITY_ID

    states = history.state_changes_during_period(hass, start_time, end_time, entity_id)
    sensor_states = states.get(entity_id, [])
    records = []
    for state in sensor_states:
        try:
            # Round timestamp to the hour (as in training)
            if state.state == "unavailable":
                continue
            dt = state.last_changed.replace(minute=0, second=0, microsecond=0)
            power = float(state.state)
            records.append({"time": dt, "power": power})
        except Exception as e:
            _LOGGER.error(f"Error processing sensor state: {e}")
    if records:
        df = pd.DataFrame(records)
        df = df.groupby("time", as_index=False).mean()

        # Create complete hourly range
        # full_range = pd.date_range(
        #    start=start_time.replace(minute=0, second=0, microsecond=0),
        #    end=end_time.replace(minute=0, second=0, microsecond=0),
        #    freq="H",
        #    tz=start_time.tzinfo,
        # )

        # Create complete DataFrame with zeros for missing hours
        # complete_df = pd.DataFrame({"time": full_range})
        # df = pd.merge(complete_df, df, on="time", how="left")
        # df["power"] = df["power"].fillna(0)

        return df.to_dict(orient="records")
    return []


def collect_sensor_csv_data(csv_file_name: str) -> list[SensorDataRecord]:
    # Read the CSV file.
    # If your CSV doesn't include a header, specify header=None and provide column names.
    df = pd.read_csv(csv_file_name)

    # Convert the Unix timestamp (with fractional seconds) to a pandas Timestamp with UTC timezone.
    df["time"] = (
        pd.to_datetime(df["last_updated_ts"], unit="s", utc=False)
        .dt.tz_localize("Europe/Prague")
        .dt.ceil("H")
    )

    # Convert the sensor state to float (assuming it's a numeric value representing power)
    df["power"] = df["state"].astype(float)
    df = df.groupby("time", as_index=False).mean()
    # Remove records where power is 0
    df = df[df["power"] > 0]
    # Create complete hourly range
    # full_range = pd.date_range(
    #    start=df["time"].min(), end=df["time"].max(), freq="H", tz=df["time"].dt.tz
    # )

    # Create complete DataFrame with zeros for missing hours
    # complete_df = pd.DataFrame({"time": full_range})
    # df = pd.merge(complete_df, df, on="time", how="left")
    # df["power"] = df["power"].fillna(0)

    return df[["time", "power"]].to_dict(orient="records")


def merge_data(meteo_records, sensor_records):
    """
    Merge meteo and sensor data on the 'time' column.
    Returns a pandas DataFrame.
    """
    df_meteo = pd.DataFrame(meteo_records)
    df_sensor = pd.DataFrame(sensor_records)
    df = pd.merge(df_meteo, df_sensor, on="time", how="inner")
    df = df.sort_values("time")
    return df


def train_model(data_df, model_path, scaler_path, epochs=50):
    """
    Train an MLP neural network regressor using the merged data.
    The data_df must include all meteo features and a 'power' column.
    Saves the trained model and scaler to the provided paths.
    """
    _LOGGER.info("Starting training with %d records", len(data_df))

    feature_cols = [
        "temperature",
        "humidity",
        "rain",
        "showers",
        "snowfall",
        "cloudcover",
        "cloudcover_low",
        "cloudcover_mid",
        "cloudcover_high",
        "visibility",
        "shortwave_radiation",
        "direct_radiation",
        "diffuse_radiation",
        "direct_normal_radiation",
        "terrestrial_radiation",
        "sun_altitude",
        "sun_azimuth",
    ]
    for col in feature_cols + ["power"]:
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
    The dictionaries must contain:
      - temperature, humidity, rain, showers, snowfall, cloudcover,
      - cloudcover_low, cloudcover_mid, cloudcover_high, visibility,
      - shortwave_radiation, direct_radiation, diffuse_radiation,
      - direct_normal_radiation, terrestrial_radiation, sun_altitude, sun_azimuth
    Returns a list of predictions.
    """
    feature_cols = [
        "temperature",
        "humidity",
        "rain",
        "showers",
        "snowfall",
        "cloudcover",
        "cloudcover_low",
        "cloudcover_mid",
        "cloudcover_high",
        "visibility",
        "shortwave_radiation",
        "direct_radiation",
        "diffuse_radiation",
        "direct_normal_radiation",
        "terrestrial_radiation",
        "sun_altitude",
        "sun_azimuth",
    ]
    df = pd.DataFrame(forecast_data)
    for col in feature_cols:
        if col not in df.columns:
            raise ValueError(f"Forecast data missing column {col}")
    X = df[feature_cols].values
    X_scaled = scaler.transform(X)
    predictions = model.predict(X_scaled)
    return predictions.flatten().tolist()
