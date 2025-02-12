# battery_forecast.py
import datetime
import logging
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

from . import const
from .config import Configuration

_LOGGER = logging.getLogger(__name__)


def forecast_battery_capacity(hass: HomeAssistant, days: int):
    """
    Forecast the battery capacity (in %) for the next 'days' days.

    Uses:
      - Current battery capacity (a sensor; entity id stored in Configuration.pv_batt_capacity_entity_id)
      - Solar panels power forecast (15-minute intervals, via hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST].get_forecast())
      - Overall power consumption forecast (hourly intervals, with keys "min", "med", "max",
        via hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION].get_forecast())
      - Maximum battery energy in Wh (Configuration.pv_batt_max_energy)
      - Minimum and maximum SOC of the battery (Configuration.pv_batt_min_soc and pv_batt_max_soc, defaulting to 10% and 90%)
      - Number of days to forecast from now.

    The simulation:
      1. Reads the current battery capacity from hass.states.
      2. Converts it to energy available (Wh).
      3. For each hour from the next full hour until now + (days * 24 hours):
         - Aggregates the solar forecast for that hour (averaging the four 15-minute forecasts).
         - Retrieves the consumption forecast for that hour.
         - Computes the net energy for each scenario:
              • scenario "min": net_energy = solar_energy - consumption_max
              • scenario "med": net_energy = solar_energy - consumption_med
              • scenario "max": net_energy = solar_energy - consumption_min
         - Updates the battery energy for each scenario and clamps it between the minimum and maximum battery energies.
         - Converts the updated energy values to capacity percentages.
         - Stores a forecast record with the timestamp (rounded down to the hour) and the three capacities.
      4. Returns the list of forecast records.

    Returns:
      A list of dictionaries with keys: "time", "min", "med", "max".
    """
    # Get configuration
    config = Configuration.get_instance()
    # Read current battery capacity (as %) from its sensor.

    current_capacity = float(hass.states.get(config.pv_batt_capacity_entity_id).state)
    # Maximum battery energy (Wh)
    max_energy = float(hass.states.get(config.pv_batt_max_energy_entity_id).state)
    # Compute current energy in Wh.
    current_energy_min = current_energy_med = current_energy_max = (
        current_capacity / 100.0 * max_energy
    )

    # Battery energy limits based on min and max SOC.
    batt_min_energy = max_energy * (
        float(hass.states.get(config.pv_batt_min_soc).state) / 100.0
    )
    batt_max_energy = max_energy * (
        float(hass.states.get(config.pv_batt_max_soc).state) / 100.0
    )

    # Get solar forecast (15-minute intervals) from its sensor.
    # Assumes the sensor object is stored in hass.data with key SENSOR_PV_POWER_FORECAST.
    solar_sensor = hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST]
    solar_forecast = (
        solar_sensor.get_forecast()
    )  # Returns a JSON array of objects with keys "time" and "power"

    # Aggregate solar forecast by hour.
    solar_by_hour = {}
    for entry in solar_forecast:
        try:
            # Parse the time (assumed ISO format)
            t = datetime.datetime.fromisoformat(entry["time"])
            # Round down to the hour.
            hour = t.replace(minute=0, second=0, microsecond=0)
            solar_by_hour.setdefault(hour, []).append(float(entry["power"]))
        except Exception as err:
            _LOGGER.error("Error processing solar forecast entry %s: %s", entry, err)
    # For each hour, average the power values.
    solar_hourly = {}
    for hour, values in solar_by_hour.items():
        solar_hourly[hour] = sum(values) / len(values)
    # Convert average power (W) to energy (Wh) for 1 hour: simply the average value (W) * 1h.
    # (Assuming forecast values are average power values.)

    # Get consumption forecast (hourly) from its sensor.
    cons_sensor = hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION]
    cons_forecast = (
        cons_sensor.get_forecast()
    )  # Returns JSON array with keys "time", "min", "med", "max"
    cons_by_hour = {}
    for entry in cons_forecast:
        try:
            t = datetime.datetime.fromisoformat(entry["time"])
            hour = t.replace(minute=0, second=0, microsecond=0)
            cons_by_hour[hour] = {
                "min": float(entry["min"]),
                "med": float(entry["med"]),
                "max": float(entry["max"]),
            }
        except Exception as err:
            _LOGGER.error(
                "Error processing consumption forecast entry %s: %s", entry, err
            )

    # Simulation: start from next full hour (in configured timezone)
    tz = ZoneInfo(config.timezone)
    now = datetime.datetime.now(tz)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    # If now is not exactly on the hour, start with the next hour.
    start_sim = (
        current_hour
        if now == current_hour
        else current_hour + datetime.timedelta(hours=1)
    )
    end_sim = start_sim + datetime.timedelta(hours=days * 24)

    forecast_results = [
        {
            "time": datetime.datetime.now(tz).isoformat(),
            "min": current_capacity,
            "med": current_capacity,
            "max": current_capacity,
        }
    ]
    sim_time = start_sim
    # For each hour in the simulation period:
    while sim_time < end_sim:
        # Solar energy for this hour (Wh): use the average solar power if available.
        solar_power = solar_hourly.get(
            sim_time, 0.0
        )  # in Wh (since 1 hour × W gives Wh)

        # Consumption forecast for this hour.
        consumption = cons_by_hour.get(sim_time, {"min": 0.0, "med": 0.0, "max": 0.0})
        # Note: For battery capacity forecast we assume:
        #   - Worst-case scenario: house consumption is highest → battery gains less energy.
        #   - Best-case scenario: house consumption is lowest → battery gains more energy.
        net_energy_min = solar_power - consumption["max"]
        net_energy_med = solar_power - consumption["med"]
        net_energy_max = solar_power - consumption["min"]

        # Update battery energy for each scenario, and clamp between battery limits.
        new_energy_min = max(
            batt_min_energy, min(batt_max_energy, current_energy_min + net_energy_min)
        )
        new_energy_med = max(
            batt_min_energy, min(batt_max_energy, current_energy_med + net_energy_med)
        )
        new_energy_max = max(
            batt_min_energy, min(batt_max_energy, current_energy_max + net_energy_max)
        )

        # Convert back to capacity in %.
        cap_min = new_energy_min / max_energy * 100.0
        cap_med = new_energy_med / max_energy * 100.0
        cap_max = new_energy_max / max_energy * 100.0

        # Append forecast for this hour.
        forecast_results.append(
            {
                "time": sim_time.isoformat(),
                "min": cap_min,
                "med": cap_med,
                "max": cap_max,
            }
        )

        # Update current energies for the next hour.
        current_energy_min = new_energy_min
        current_energy_med = new_energy_med
        current_energy_max = new_energy_max

        # Move to the next hour.
        sim_time += datetime.timedelta(hours=1)

    return forecast_results
