# battery_grid_forecast.py

import datetime
from zoneinfo import ZoneInfo
import logging

from homeassistant.core import HomeAssistant

from .config import Configuration
from . import const

_LOGGER = logging.getLogger(__name__)


def forecast_grid(hass: HomeAssistant, days: int):
    """
    Forecast energy export/import to the grid for the next `days` days.

    Uses:
      - Solar forecast from hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST]
        (15-minute intervals; aggregated to hourly averages)
      - Consumption forecast from hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION]
        (hourly intervals; with fields "min", "med", "max")
      - Battery forecast from hass.data[const.DOMAIN][const.SENSOR_PV_BATTERY_FORECAST]
        (hourly intervals; with fields "min", "med", "max", representing predicted battery capacity in %)
      - Battery SOC threshold sensors:
          - Minimum SOC threshold: hass.states.get(config.pv_batt_min_soc).state
          - Maximum SOC threshold: hass.states.get(config.pv_batt_max_soc).state

    Logic:
      - For each forecast hour:
          - Aggregate the solar forecast (average of all 15-min values in that hour).
          - Use the consumption forecast for that hour.
          - Use the battery forecast for that hour (for each scenario: min, med, max).
          - Then:
             * If (solar > consumption) and battery is at or above the max threshold,
               grid export = (solar - consumption) (for that scenario).
             * If (consumption > solar) and battery is at or below the min threshold,
               grid import = (consumption - solar) (for that scenario).
             * Otherwise, grid exchange is zero.

    Returns:
      A list of dictionaries, each with keys "time", "min", "med", "max".
    """
    config = Configuration.get_instance()

    # Retrieve forecasts from sensors
    # (Make sure your sensors are already stored in hass.data with proper keys)
    solar_sensor = hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST]
    cons_sensor = hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION]
    batt_sensor = hass.data[const.DOMAIN][const.SENSOR_PV_BATTERY_FORECAST]

    try:
        solar_forecast = (
            solar_sensor.get_forecast()
        )  # List of dicts with "time" and "power" (15-min intervals)
    except Exception as e:
        _LOGGER.error("Error retrieving solar forecast: %s", e)
        solar_forecast = []
    try:
        cons_forecast = (
            cons_sensor.get_forecast()
        )  # List of dicts with "time", "min", "med", "max" (hourly)
    except Exception as e:
        _LOGGER.error("Error retrieving consumption forecast: %s", e)
        cons_forecast = []
    try:
        batt_forecast = (
            batt_sensor.get_forecast()
        )  # List of dicts with "time", "min", "med", "max" (hourly, battery capacity %)
    except Exception as e:
        _LOGGER.error("Error retrieving battery forecast: %s", e)
        batt_forecast = []

    # Aggregate solar forecast into hourly averages.
    solar_by_hour = {}
    for entry in solar_forecast:
        try:
            t = datetime.datetime.fromisoformat(entry["time"])
            # Round down to the hour.
            t_hour = t.replace(minute=0, second=0, microsecond=0)
            solar_by_hour.setdefault(t_hour, []).append(float(entry["power"]))
        except Exception as err:
            _LOGGER.error("Error processing solar forecast entry %s: %s", entry, err)
    solar_hourly = {}
    for t_hour, values in solar_by_hour.items():
        solar_hourly[t_hour] = sum(values) / len(values)

    # Convert consumption forecast into a dict keyed by hour.
    cons_by_hour = {}
    for entry in cons_forecast:
        try:
            t = datetime.datetime.fromisoformat(entry["time"])
            t_hour = t.replace(minute=0, second=0, microsecond=0)
            cons_by_hour[t_hour] = {
                "min": float(entry["min"]),
                "med": float(entry["med"]),
                "max": float(entry["max"]),
            }
        except Exception as err:
            _LOGGER.error(
                "Error processing consumption forecast entry %s: %s", entry, err
            )

    # Convert battery forecast into a dict keyed by hour.
    batt_by_hour = {}
    for entry in batt_forecast:
        try:
            t = datetime.datetime.fromisoformat(entry["time"])
            t_hour = t.replace(minute=0, second=0, microsecond=0)
            batt_by_hour[t_hour] = entry  # Contains keys "min", "med", "max" (in %)
        except Exception as err:
            _LOGGER.error("Error processing battery forecast entry %s: %s", entry, err)

    # Get battery SOC thresholds from sensors (they should be numeric strings)
    try:
        batt_min_threshold = float(hass.states.get(config.pv_batt_min_soc).state)
    except Exception as err:
        _LOGGER.error("Error reading pv_batt_min_soc: %s", err)
        batt_min_threshold = 10.0
    try:
        batt_max_threshold = float(hass.states.get(config.pv_batt_max_soc).state)
    except Exception as err:
        _LOGGER.error("Error reading pv_batt_max_soc: %s", err)
        batt_max_threshold = 90.0

    # Determine simulation time range: from the next full hour until (days*24) hours ahead.
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

    sim_time = start_sim
    while sim_time < end_sim:
        # Get solar forecast for this hour (Wh)
        solar_power = solar_hourly.get(sim_time, 0.0)
        # Get consumption forecast for this hour.
        cons = cons_by_hour.get(sim_time, {"min": 0.0, "med": 0.0, "max": 0.0})
        # Get battery forecast for this hour.
        batt = batt_by_hour.get(sim_time, {"min": None, "med": None, "max": None})

        # For each scenario, determine grid exchange.
        # Scenario "min": using consumption forecast "max" (worst-case) and battery forecast "min"
        grid_min = 0.0
        if batt.get("min") is not None:
            if solar_power > cons["min"] and float(batt["max"]) >= batt_max_threshold:
                grid_min = solar_power - cons["min"]
            elif solar_power < cons["min"] and float(batt["max"]) <= batt_min_threshold:
                grid_min = cons["min"] - solar_power

        # Scenario "med": using consumption forecast "med" and battery forecast "med"
        grid_med = 0.0
        if batt.get("med") is not None:
            if solar_power > cons["med"] and float(batt["med"]) >= batt_max_threshold:
                grid_med = solar_power - cons["med"]
            elif solar_power < cons["med"] and float(batt["med"]) <= batt_min_threshold:
                grid_med = cons["med"] - solar_power

        # Scenario "max": using consumption forecast "min" (best-case consumption) and battery forecast "max"
        grid_max = 0.0
        if batt.get("max") is not None:
            if solar_power > cons["max"] and float(batt["min"]) >= batt_max_threshold:
                grid_max = solar_power - cons["max"]
            elif solar_power < cons["max"] and float(batt["min"]) <= batt_min_threshold:
                grid_max = cons["max"] - solar_power

        grid_forecast.append(
            {
                "time": sim_time.isoformat(),
                "min": grid_min,
                "med": grid_med,
                "max": grid_max,
            }
        )

        sim_time += datetime.timedelta(hours=1)

    return grid_forecast
