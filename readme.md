# HASS Solar Forecast ML

An integration to forecast solar power production using historical production and meteorological data with Machine Learning (ML).

## Features

- Provides real-time solar power forecasts.
- Uses historical data and weather information processed with ML.
- Exposes sensors/entities to Home Assistant for automations and monitoring.

## Installation

- Manual Installation:
  1. Place the integration in your Home Assistant's `custom_components/solar_forecast_ml` folder.
  2. Restart Home Assistant.

- HACS Installation:
  1. Open Home Assistant Community Store (HACS).
  2. Go to Settings > Custom repositories.
  3. Add this repository: https://github.com/your_username/your_repo (set category to "Integration").
  4. After adding, search for "HASS Solar Forecast ML" and install the integration.
  5. Restart Home Assistant.

### Docker Installation (Raspberry Pi)
If running Home Assistant in Docker on a Raspberry Pi, you may encounter issues with installing scikit‑learn. To fix this, create a custom Docker image with scikit‑learn pre-installed. For example:

```dockerfile
# Use the official Home Assistant image as the base
FROM ghcr.io/home-assistant/home-assistant:stable

# Install build dependencies and headers needed for scikit‑learn and its dependencies
RUN apk add --no-cache \
      ninja \
      build-base \
      gfortran \
      openblas-dev \
      linux-headers

# Pre-install scikit‑learn using PiWheels so that Home Assistant finds it at startup
RUN pip install --extra-index-url https://www.piwheels.org/simple scikit-learn
```

Then, use this custom image to run Home Assistant.

## Configuration

The integration is primarily configured via the UI. The available configuration options are:

- latitude (string): Your latitude. Default is "50.08804".
- longitude (string): Your longitude. Default is "14.42076".
- timezone (string): Your timezone (e.g., "Europe/Prague").
- pv_power_entity: Sensor entity for photovoltaic (PV) panels power (W).
- power_consumption_entity: Sensor entity for house power consumption (Wh).
- batt_capacity_entity: Sensor entity for current battery capacity (%).
- batt_max_energy_entity: Sensor entity for the battery's maximum energy (Wh).
- batt_min_soc_entity: Sensor entity for the battery's minimum state of charge (%).
- batt_max_soc_entity: Sensor entity for the battery's maximum state of charge (%).
- batt_max_power (integer): Battery maximum power. Default is 10000 (W).

For manual YAML configuration, you can use a snippet like this:

```yaml
solar_forecast_ml:
  latitude: "50.08804"
  longitude: "14.42076"
  timezone: "Europe/Prague"
  pv_power_entity: sensor.pv_power
  power_consumption_entity: sensor.power_consumption
  batt_capacity_entity: sensor.battery_capacity
  batt_max_energy_entity: sensor.battery_max_energy
  batt_min_soc_entity: sensor.battery_min_soc
  batt_max_soc_entity: sensor.battery_max_soc
  batt_max_power: 10000
```

## Usage

Once installed and configured, the integration will create sensors and services for solar forecasting.
- Check the Home Assistant logs for startup messages.
- Use the provided sensors in your dashboards and automations.

## Troubleshooting

- Verify that the API key and configurations are correct.
- Check logs for potential errors.
- Review issues on GitHub if problems persist.

## Contributing

Contributions are welcome! Please open issues or pull requests on GitHub.

## License

Licensed under the MIT License.