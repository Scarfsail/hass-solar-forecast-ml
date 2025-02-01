import logging
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun
import joblib
import pandas as pd
import requests
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

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


def is_daytime(dt):
    """Return True if dt is between sunrise and sunset."""
    s = sun(LOCATION.observer, date=dt.date(), tzinfo=dt.tzinfo)
    return s["sunrise"] <= dt <= s["sunset"]


def get_sun_position(dt):
    """
    Return sun altitude and azimuth for a given datetime.
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


def collect_meteo_data(from_date, to_date):
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
        f"&start_date={from_date:%Y-%m-%d}&end_date={to_date:%Y-%m-%d}"
    )
    response = requests.get(url)
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
            if not is_daytime(dt):
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


def collect_forecast_meteo_data(from_dt, to_dt):
    """
    Collect forecast meteo data from Open-Meteo for the given datetime range.
    The API is queried at hourly resolution.
    Returns a list of dictionaries (one per hour) with all required features.
    """

    start_date = from_dt.date()
    end_date = to_dt.date()
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&hourly=temperature_2m,relativehumidity_2m,rain,showers,snowfall,cloudcover,"
        "cloudcover_low,cloudcover_mid,cloudcover_high,visibility,shortwave_radiation,"
        "direct_radiation,diffuse_radiation,direct_normal_irradiance,terrestrial_radiation"
        f"&start_date={start_date:%Y-%m-%d}&end_date={end_date:%Y-%m-%d}"
    )
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    hourly = data.get("hourly", {})

    # Build a DataFrame from the hourly data.
    times = pd.to_datetime(hourly.get("time", []))
    # Ensure all times are timezone-aware.
    from zoneinfo import ZoneInfo

    times = times.map(
        lambda t: t if t.tzinfo else t.replace(tzinfo=ZoneInfo("Europe/Prague"))
    )

    df = pd.DataFrame(
        {
            "time": times,
            "temperature": hourly.get("temperature_2m", []),
            "humidity": hourly.get("relativehumidity_2m", []),
            "rain": hourly.get("rain", []),
            "showers": hourly.get("showers", []),
            "snowfall": hourly.get("snowfall", []),
            "cloudcover": hourly.get("cloudcover", []),
            "cloudcover_low": hourly.get("cloudcover_low", []),
            "cloudcover_mid": hourly.get("cloudcover_mid", []),
            "cloudcover_high": hourly.get("cloudcover_high", []),
            "visibility": hourly.get("visibility", []),
            "shortwave_radiation": hourly.get("shortwave_radiation", []),
            "direct_radiation": hourly.get("direct_radiation", []),
            "diffuse_radiation": hourly.get("diffuse_radiation", []),
            "direct_normal_radiation": hourly.get("direct_normal_irradiance", []),
            "terrestrial_radiation": hourly.get("terrestrial_radiation", []),
        }
    )

    # Filter the data to include only the rows within the provided datetime range.
    df = df[(df["time"] >= from_dt) & (df["time"] <= to_dt)]

    # Compute sun position for each timestamp.
    df["sun_altitude"], df["sun_azimuth"] = zip(
        *df["time"].apply(lambda dt: get_sun_position(dt))
    )

    # Return the records as a list of dictionaries.
    records = df.to_dict(orient="records")
    return records


def collect_sensor_data(hass, start_time, end_time, entity_id=PV_POWER_ENTITY_ID):
    """
    Collect historical sensor data from Home Assistant for the given entity.
    Returns a list of dictionaries with keys 'time' and 'power'.
    Uses the recorder's history API.
    """
    from homeassistant.components.recorder import history

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
        return df.to_dict(orient="records")
    return []


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
        hidden_layer_sizes=(64, 32), activation="relu", solver="adam", max_iter=500
    )
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
