import datetime
import logging
from typing import TypedDict

from astral.sun import sun
import pandas as pd
import requests

from homeassistant.components.recorder import history

from .config import Configuration

_LOGGER = logging.getLogger(__name__)

# Define meteo parameters - use same names for API and records
METEO_PARAMS = [
    "temperature_2m",
    "direct_radiation",
    "diffuse_radiation",
    "direct_normal_irradiance",
]


class SensorDataRecord(TypedDict):
    time: pd.Timestamp
    power: float


def is_daytime(dt: datetime):
    """Return True if dt is between sunrise and sunset."""
    cfg = Configuration.get_instance()
    s = sun(cfg.location.observer, date=dt.date(), tzinfo=dt.tzinfo)
    dawn = s["dawn"] - datetime.timedelta(hours=1)
    dusk = s["dusk"] + datetime.timedelta(hours=1)
    return dawn <= dt <= dusk


def collect_meteo_data(from_date, to_date, skip_night=True):
    """
    Collect historical meteo data from the Open-Meteo API between from_date and to_date.
    The dates must be datetime.date objects.
    Returns a list of dictionaries (one per hour, daytime only).
    """
    cfg = Configuration.get_instance()
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={cfg.latitude}&longitude={cfg.longitude}"
        f"&minutely_15={','.join(METEO_PARAMS)}"
        f"&start_date={from_date:%Y-%m-%d}&end_date={to_date:%Y-%m-%d}"
    )
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    minutely_15 = data.get("minutely_15", {})
    records = []
    times = minutely_15.get("time", [])
    for i, time in enumerate(times):
        try:
            dt = pd.to_datetime(time, utc=True).tz_convert(cfg.timezone)

            # Ensure dt is timezone-aware.

            # if dt.tzinfo is None:
            #     dt = dt.replace(tzinfo=ZoneInfo("Europe/Prague"))

            # Only include daytime records
            if not is_daytime(dt) and skip_night:
                continue

            record = {"time": dt}

            # Add all meteo parameters to the record
            for param in METEO_PARAMS:
                record[param] = float(minutely_15[param][i])

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
    cfg = Configuration.get_instance()
    entity_id = cfg.pv_power_entity_id

    states = history.state_changes_during_period(hass, start_time, end_time, entity_id)
    sensor_states = states.get(entity_id, [])
    records = []
    for state in sensor_states:
        try:
            # Round timestamp to the hour (as in training)
            if state.state == "unavailable":
                continue
            dt = state.last_changed.tz_convert(cfg.timezone).floor("15min")
            power = float(state.state)
            records.append({"time": dt, "power": power})
        except Exception as e:
            _LOGGER.error(f"Error processing sensor state: {e}")
    if records:
        df = pd.DataFrame(records)
        df = df.groupby("time", as_index=False).mean()
        df = df[df["power"] > 0]

        return df.to_dict(orient="records")
    return []


def collect_sensor_csv_data(csv_file_name: str) -> list[SensorDataRecord]:
    # Read the CSV file.
    # If your CSV doesn't include a header, specify header=None and provide column names.
    df = pd.read_csv(csv_file_name)

    # Convert the Unix timestamp (with fractional seconds) to a pandas Timestamp with UTC timezone.
    cfg = Configuration.get_instance()
    df["time"] = (
        pd.to_datetime(df["last_updated_ts"], unit="s", utc=True)
        .dt.tz_convert(cfg.timezone)
        .dt.floor("15min")
    )

    # Convert the sensor state to float (assuming it's a numeric value representing power)
    df["power"] = df["state"].astype(float)
    df = df.groupby("time", as_index=False).mean()
    # Remove records where power is 0
    df = df[df["power"] > 0]

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
