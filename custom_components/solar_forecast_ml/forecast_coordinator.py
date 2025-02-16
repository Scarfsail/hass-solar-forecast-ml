from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import forecast_battery, forecast_consumption, forecast_grid, forecast_solar
from .config import Configuration

_LOGGER = logging.getLogger(__name__)

PREDICT_DAYS_FORWARD = 7
PREDICT_DAYS_BACK = 3


class ForecastCoordinator(DataUpdateCoordinator):
    """Coordinator to run periodic prediction and training tasks sequentially for solar_forecast_ml."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.config = Configuration.get_instance()
        self.first_update = True  # Force full predictions on integration startup

        super().__init__(
            hass,
            _LOGGER,
            name="solar_forecast_ml_coordinator",
            update_interval=timedelta(minutes=1),
            always_update=True,
        )

    async def _async_update_data(self):
        """Run training tasks at midnight and prediction tasks based on the schedule.

        On startup, all predictions (solar, consumption, battery, grid) run in sequence.
        Subsequently, solar and consumption predictions run only on 15-minute ticks,
        while battery and grid predictions run every minute.
        """

        now = datetime.now(ZoneInfo(self.config.timezone))
        tasks: list[tuple[str, callable]] = []

        # --- Training Tasks once per day ---
        # Check if solar model needs training
        training_start_date = now - timedelta(days=60)
        training_end_date = now - timedelta(hours=1)

        if not forecast_solar.is_model_trained() or (
            now - forecast_solar.when_model_was_trained()
        ) > timedelta(hours=24):
            tasks.append(
                (
                    "Solar training",
                    lambda: forecast_solar.collect_and_train(
                        self.hass, training_start_date, training_end_date
                    ),
                )
            )
        if not forecast_consumption.is_model_trained() or (
            now - forecast_consumption.when_model_was_trained()
        ) > timedelta(hours=24):
            tasks.append(
                (
                    "Consumption training",
                    lambda: forecast_consumption.collect_and_train(
                        self.hass, training_start_date, training_end_date
                    ),
                )
            )

        # Define the prediction window used by solar and consumption predictions.
        prediction_from = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=PREDICT_DAYS_BACK)
            + timedelta(seconds=1)
        )
        prediction_to = (
            prediction_from
            + timedelta(days=PREDICT_DAYS_FORWARD)
            - timedelta(seconds=1)
        )

        # --- Prediction Tasks ---
        # On startup or every 15 minutes, run solar and consumption predictions.
        if self.first_update or now.minute % 15 == 0:
            tasks.append(
                (
                    "Solar prediction",
                    lambda: forecast_solar.collect_and_predict(
                        self.hass, prediction_from, prediction_to
                    ),
                )
            )
            tasks.append(
                (
                    "Consumption prediction",
                    lambda: forecast_consumption.generate_predictions(
                        self.hass, prediction_from, prediction_to, self.config.timezone
                    ),
                )
            )
            if self.first_update:
                self.first_update = False

        # Battery and grid predictions always run every minute.
        tasks.append(
            (
                "Battery prediction",
                lambda: self.hass.async_add_executor_job(
                    forecast_battery.forecast_battery_capacity,
                    self.hass,
                    PREDICT_DAYS_FORWARD,
                ),
            )
        )
        tasks.append(
            (
                "Grid prediction",
                lambda: self.hass.async_add_executor_job(
                    forecast_grid.forecast_grid, self.hass, PREDICT_DAYS_FORWARD
                ),
            )
        )

        # --- Execute Tasks Sequentially ---
        for task_name, task_callable in tasks:
            try:
                await task_callable()
                _LOGGER.info("%s completed successfully", task_name)
            except Exception as e:
                _LOGGER.error("Error during %s: %s", task_name, e)

        self._schedule_refresh()

        return {"status": "updated", "updated_at": now.isoformat()}
