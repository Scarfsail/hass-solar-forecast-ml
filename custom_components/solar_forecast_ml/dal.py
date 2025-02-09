import datetime
import logging
from typing import TypedDict

from astral.sun import sun
import pandas as pd
import requests
import sqlalchemy as sa

from homeassistant.components.recorder import get_instance, history
from homeassistant.components.recorder.models import state

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


def get_aggregated_states(
    hass,
    start_time: datetime,
    end_time: datetime,
    entity_id: str,
    interval_minutes: int = 15,
):
    """
    Retrieve aggregated states for the given entity between start_time and end_time,
    grouping records into intervals of 'interval_minutes' minutes.

    This function uses the last_updated_ts column (which is a UNIX timestamp) for grouping.
    It builds a different SQL expression depending on whether the backend is SQLite or MySQL/MariaDB.
    """
    # Get the recorder instance and its engine.
    recorder_instance = get_instance(hass)
    engine = recorder_instance.engine

    # Reflect the states table.
    metadata = sa.MetaData()
    states_table = sa.Table("states", metadata, autoload_with=engine)
    states_meta_table = sa.Table("states_meta", metadata, autoload_with=engine)
    # Get the metadata_id for the given entity_id.
    metadata_id_query = sa.select(states_meta_table.c.metadata_id).where(
        states_meta_table.c.entity_id == entity_id
    )

    with engine.connect() as conn:
        metadata_id_result = conn.execute(metadata_id_query).scalar()

        if metadata_id_result is None:
            raise ValueError(f"No metadata found for entity_id: {entity_id}")

        interval_seconds = interval_minutes * 60

        # Build a dialect-aware expression for the time interval based on last_updated_ts.
        if engine.dialect.name == "sqlite":
            # For SQLite, last_updated_ts is already a UNIX timestamp.
            # We cast it to integer, divide by interval_seconds, multiply back,
            # and then convert it to a datetime string using the 'unixepoch' modifier.
            time_interval_expr = (
                (
                    sa.func.cast(states_table.c.last_updated_ts, sa.Integer)
                    // interval_seconds
                )
                * interval_seconds
            ).label("time_interval")
        elif engine.dialect.name in ("mysql", "mariadb"):
            # For MySQL/MariaDB, use from_unixtime directly.
            time_interval_expr = (
                sa.func.floor(states_table.c.last_updated_ts / interval_seconds)
                * interval_seconds
            ).label("time_interval")
        else:
            raise RuntimeError(f"Unsupported database dialect: {engine.dialect.name}")
        start_time_ts = start_time.timestamp()
        end_time_ts = end_time.timestamp()

        query = (
            sa.select(
                time_interval_expr,
                sa.func.avg(sa.cast(states_table.c.state, sa.Float)).label("avg_state"),
                sa.func.count().label("count_records"),
            )
            .where(
                sa.and_(
                    states_table.c.state != "unavailable",
                    states_table.c.metadata_id == metadata_id_result,
                    states_table.c.last_updated_ts >= start_time_ts,
                    states_table.c.last_updated_ts < end_time_ts,
                )
            )
            .group_by("time_interval")
            .order_by("time_interval")
        )

        result = conn.execute(query)
        rows = result.fetchall()

    return rows


def collect_pv_power_historical_data(
    hass, start_time, end_time
) -> list[SensorDataRecord]:
    cfg = Configuration.get_instance()
    entity_id = cfg.pv_power_entity_id

    aggregated = get_aggregated_states(
        hass, start_time, end_time, entity_id, interval_minutes=15
    )

    return convert_pv_power_data_to_dict(
        pd.DataFrame(aggregated), "time_interval", "avg_state"
    )


def collect_pv_power_csv_data(csv_file_name: str) -> list[SensorDataRecord]:
    return convert_pv_power_data_to_dict(
        pd.read_csv(csv_file_name), "last_updated_ts", "state"
    )


def convert_pv_power_data_to_dict(
    sensor_data: pd.DataFrame, time_column: str, power_column: str
) -> list[SensorDataRecord]:
    cfg = Configuration.get_instance()

    sensor_data["time"] = pd.to_datetime(
        sensor_data[time_column], unit="s", utc=True
    ).dt.tz_convert(cfg.timezone)
    sensor_data["power"] = sensor_data[power_column].astype(float)
    sensor_data = sensor_data[["time", "power"]]
    sensor_data = sensor_data[sensor_data["power"] > 0]
    return sensor_data.to_dict(orient="records")


def merge_meteo_and_pv_power_data(meteo_records, pv_power_records):
    """
    Merge meteo and sensor data on the 'time' column.
    Returns a pandas DataFrame.
    """
    df_meteo = pd.DataFrame(meteo_records)
    df_sensor = pd.DataFrame(pv_power_records)
    df = pd.merge(df_meteo, df_sensor, on="time", how="inner")
    df = df.sort_values("time")
    return df


def collect_consumption_data(hass, start_time, end_time):
    """
    Collect historical energy consumption data from the given sensor between start_time and end_time.
    Returns a DataFrame with one record per hour (averaged if multiple records exist)
    and adds features: hour (0-23) and day_of_week (Monday=0, Sunday=6).
    """
    cfg = Configuration.get_instance()
    sensor_id = cfg.power_consumption_entity_id
    aggregated = get_aggregated_states(
        hass, start_time, end_time, sensor_id, interval_minutes=60
    )

    if aggregated:
        df = pd.DataFrame(aggregated)
        df["time"] = pd.to_datetime(
            df["time_interval"], unit="s", utc=True
        ).dt.tz_convert(cfg.timezone)
        df["hour"] = df["time"].dt.hour
        df["day_of_week"] = df["time"].dt.dayofweek
        df["power"] = df["avg_state"].astype(float)
        return df[["hour", "day_of_week", "power"]]
    return pd.DataFrame()
