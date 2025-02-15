# battery_grid_forecast.py

import datetime
from zoneinfo import ZoneInfo
import logging
from typing import Dict, List, Union
import pandas as pd

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import run_callback_threadsafe
from .config import Configuration
from . import const

_LOGGER = logging.getLogger(__name__)


def _calculate_grid_exchange(
    solar_power: float,
    consumption: float,
    battery_soc: float,
    batt_min_threshold: float,
    batt_max_threshold: float,
) -> float:
    """Calculate grid exchange based on power flows and battery state."""
    if solar_power > consumption and battery_soc >= batt_max_threshold:
        return solar_power - consumption
    elif solar_power < consumption and battery_soc <= batt_min_threshold:
        return -(consumption - solar_power)
    return 0.0


def forecast_grid(hass: HomeAssistant, days: int):
    """Forecast energy export/import to the grid for the next `days` days."""
    _LOGGER.info("Forecasting grid export/import for the next %d days", days)
    config = Configuration.get_instance()

    # Get all required sensors
    sensors = {
        "solar": hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST],
        "consumption": hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION],
        "battery": hass.data[const.DOMAIN][const.SENSOR_PV_BATTERY_FORECAST],
    }

    # Get forecasts and convert to DataFrames
    try:
        solar_df = pd.DataFrame(sensors["solar"].get_forecast())
        solar_df["time"] = pd.to_datetime(solar_df["time"], format="ISO8601")
        solar_df["hour"] = solar_df["time"].dt.floor("h")
        solar_hourly = solar_df.groupby("hour")["power"].mean()
    except Exception as e:
        _LOGGER.error("Error processing solar forecast: %s", e)
        return

    try:
        cons_df = pd.DataFrame(sensors["consumption"].get_forecast())
        cons_df["time"] = pd.to_datetime(cons_df["time"], format="ISO8601")
        cons_df.set_index("time", inplace=True)
    except Exception as e:
        _LOGGER.error("Error processing consumption forecast: %s", e)
        return

    try:
        batt_df = pd.DataFrame(sensors["battery"].get_forecast())
        batt_df["time"] = pd.to_datetime(batt_df["time"], format="ISO8601")
        batt_df.set_index("time", inplace=True)
    except Exception as e:
        _LOGGER.error("Error processing battery forecast: %s", e)
        return

    # Get battery thresholds
    try:
        batt_thresholds = {
            "min": float(hass.states.get(config.pv_batt_min_soc).state),
            "max": float(hass.states.get(config.pv_batt_max_soc).state),
        }
    except Exception as e:
        _LOGGER.error("Error reading battery thresholds: %s", e)
        batt_thresholds = {"min": 10.0, "max": 90.0}

    # Setup simulation timeframe
    tz = ZoneInfo(config.timezone)
    now = datetime.datetime.now(tz)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    start_sim = (
        current_hour
        if now == current_hour
        else current_hour + datetime.timedelta(hours=1)
    )
    end_sim = start_sim + datetime.timedelta(hours=days * 24)

    grid_forecast = []

    # Simulation loop
    sim_time = start_sim
    while sim_time < end_sim:
        solar_power = solar_hourly.get(sim_time, 0.0)

        try:
            cons = cons_df.loc[sim_time]
            batt = batt_df.loc[sim_time]

            # Calculate grid exchange for each scenario
            grid_values = {
                "min": _calculate_grid_exchange(
                    solar_power,
                    cons["min"],
                    float(batt["max"]),
                    batt_thresholds["min"],
                    batt_thresholds["max"],
                ),
                "med": _calculate_grid_exchange(
                    solar_power,
                    cons["med"],
                    float(batt["med"]),
                    batt_thresholds["min"],
                    batt_thresholds["max"],
                ),
                "max": _calculate_grid_exchange(
                    solar_power,
                    cons["max"],
                    float(batt["min"]),
                    batt_thresholds["min"],
                    batt_thresholds["max"],
                ),
            }

            grid_forecast.append({"time": sim_time.isoformat(), **grid_values})

        except KeyError:
            grid_forecast.append(
                {"time": sim_time.isoformat(), "min": 0.0, "med": 0.0, "max": 0.0}
            )

        sim_time += datetime.timedelta(hours=1)
    run_callback_threadsafe(
        hass.loop,
        hass.data[const.DOMAIN][const.SENSOR_GRID_FORECAST].update_forecast,
        grid_forecast,
    )
    _LOGGER.info(
        "Grid forecast completed successfully with %d records",
        len(grid_forecast),
    )
