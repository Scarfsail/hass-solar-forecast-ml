import datetime
import logging
from zoneinfo import ZoneInfo

import pandas as pd

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import run_callback_threadsafe

from . import const
from .config import Configuration

_LOGGER = logging.getLogger(__name__)


def _calculate_battery_energy(
    net_energy, current_energy, config, batt_max_energy, batt_min_energy
):
    """Helper function to calculate new battery energy based on net energy input"""
    if net_energy > 0 and current_energy < batt_max_energy:
        # Battery is not full and there is surplus
        charge = min(net_energy, config.pv_batt_max_power)
        new_energy = current_energy + charge
    else:
        new_energy = current_energy + net_energy

    return max(batt_min_energy, min(batt_max_energy, new_energy))


def forecast_battery_capacity(hass: HomeAssistant, days: int):
    """Forecast the battery capacity (in %) for the next 'days' days."""
    _LOGGER.info("Forecasting battery capacity for the next %d days", days)
    config = Configuration.get_instance()

    # Get battery configuration
    current_capacity = float(hass.states.get(config.pv_batt_capacity_entity_id).state)
    max_energy = float(hass.states.get(config.pv_batt_max_energy_entity_id).state)
    current_energy = current_capacity / 100.0 * max_energy

    batt_min_energy = max_energy * (
        float(hass.states.get(config.pv_batt_min_soc).state) / 100.0
    )
    batt_max_energy = max_energy * (
        float(hass.states.get(config.pv_batt_max_soc).state) / 100.0
    )

    # Get solar forecast and convert to pandas DataFrame
    solar_forecast = pd.DataFrame(
        hass.data[const.DOMAIN][const.SENSOR_PV_POWER_FORECAST].get_forecast()
    )
    solar_forecast["time"] = pd.to_datetime(solar_forecast["time"])
    solar_forecast["hour"] = solar_forecast["time"].dt.floor(
        "h"
    )  # Changed from "H" to "h"

    # Aggregate solar forecast by hour
    solar_hourly = solar_forecast.groupby("hour")["power"].mean().to_dict()

    # Get consumption forecast and convert to pandas DataFrame
    cons_forecast = pd.DataFrame(
        hass.data[const.DOMAIN][const.SENSOR_POWER_CONSUMPTION].get_forecast()
    )
    cons_forecast["time"] = pd.to_datetime(cons_forecast["time"])
    cons_forecast.set_index("time", inplace=True)

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

    # Initialize forecast results with current state
    forecast_results = [
        {
            "time": now.isoformat(),
            "min": current_capacity,
            "med": current_capacity,
            "max": current_capacity,
        }
    ]

    # Track energy levels for each scenario
    current_energies = {
        "min": current_energy,
        "med": current_energy,
        "max": current_energy,
    }

    # Simulation loop
    sim_time = start_sim
    while sim_time < end_sim:
        solar_power = solar_hourly.get(sim_time, 0.0)

        try:
            cons = cons_forecast.loc[sim_time]
            consumption = {
                "min": float(cons["min"]),
                "med": float(cons["med"]),
                "max": float(cons["max"]),
            }
        except KeyError:
            consumption = {"min": 0.0, "med": 0.0, "max": 0.0}

        # Calculate net energy for each scenario
        net_energies = {
            "min": solar_power - consumption["max"],
            "med": solar_power - consumption["med"],
            "max": solar_power - consumption["min"],
        }

        # Update battery energy for each scenario
        new_energies = {
            scenario: _calculate_battery_energy(
                net_energies[scenario],
                current_energies[scenario],
                config,
                batt_max_energy,
                batt_min_energy,
            )
            for scenario in ["min", "med", "max"]
        }

        # Convert to capacity percentage
        capacities = {
            scenario: (energy / max_energy * 100.0)
            for scenario, energy in new_energies.items()
        }

        forecast_results.append({"time": sim_time.isoformat(), **capacities})

        current_energies = new_energies
        sim_time += datetime.timedelta(hours=1)

    # Update the sensor. Assume your sensor is stored in hass.data under the key SENSOR_PV_BATTERY_FORECAST.
    run_callback_threadsafe(
        hass.loop,
        hass.data[const.DOMAIN][const.SENSOR_PV_BATTERY_FORECAST].update_forecast,
        forecast_results,
    )  # Pass the JSON forecast data.
    _LOGGER.info(
        "Battery capacity forecast completed successfully with %d records",
        len(forecast_results),
    )
