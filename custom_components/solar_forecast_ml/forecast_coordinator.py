from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, Optional
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    const,
    forecast_battery,
    forecast_consumption,
    forecast_grid,
    forecast_solar,
)
from .config import Configuration
from .forecast_data import ForecastData

_LOGGER = logging.getLogger(__name__)

PREDICT_DAYS_FORWARD = 7
PREDICT_DAYS_BACK = 0


@dataclass
class TrainingTask:
    """Represents a model training task."""

    name: str
    training_interval: timedelta
    is_trained_check: Callable[[], bool]
    last_trained_check: Callable[[], Optional[datetime]]
    train_callable: Callable[[HomeAssistant, datetime, datetime], Any]

    def needs_training(self, now: datetime) -> bool:
        """Check if model needs training based on last training time."""
        if not self.is_trained_check():
            return True
        last_trained = self.last_trained_check()
        if not last_trained:
            return True
        return (now - last_trained) > self.training_interval


@dataclass
class PredictionTask:
    """Represents a prediction task."""

    name: str
    update_interval: timedelta
    forecast_key: str
    predict_callable: Callable[..., ForecastData]
    last_run: Optional[datetime] = None

    def needs_update(self, now: datetime) -> bool:
        """Check if prediction needs to be updated."""
        if self.last_run is None:
            return True
        return (now - self.last_run) >= self.update_interval

    def mark_updated(self, now: datetime) -> None:
        """Mark task as updated."""
        self.last_run = now


def _get_prediction_window(
    now: datetime, days_back: int, days_forward: int
) -> tuple[datetime, datetime]:
    """Calculate prediction window."""
    prediction_from = (
        now.replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=days_back)
        + timedelta(seconds=1)
    )
    prediction_to = (
        prediction_from + timedelta(days=days_forward) - timedelta(seconds=1)
    )
    return prediction_from, prediction_to


class ForecastCoordinator(DataUpdateCoordinator[dict[str, ForecastData]]):
    """Coordinator to run periodic prediction and training tasks sequentially."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.config = Configuration.get_instance()
        self.forecasts: dict[str, ForecastData] = {}

        self.training_tasks = self._create_training_tasks()
        self.prediction_tasks = self._create_prediction_tasks()

        super().__init__(
            hass,
            _LOGGER,
            name="solar_forecast_ml_coordinator",
            update_interval=timedelta(minutes=1),
            always_update=True,
        )

    def _create_training_tasks(self):
        return [
            TrainingTask(
                name="Solar training",
                training_interval=timedelta(hours=24),
                is_trained_check=forecast_solar.is_model_trained,
                last_trained_check=forecast_solar.when_model_was_trained,
                train_callable=forecast_solar.collect_and_train,
            ),
            TrainingTask(
                name="Consumption training",
                training_interval=timedelta(hours=24),
                is_trained_check=forecast_consumption.is_model_trained,
                last_trained_check=forecast_consumption.when_model_was_trained,
                train_callable=forecast_consumption.collect_and_train,
            ),
        ]

    def _create_prediction_tasks(self):
        return [
            PredictionTask(
                name="Solar prediction",
                update_interval=timedelta(minutes=15),
                forecast_key=const.FORECAST_DATA_PV_POWER,
                predict_callable=lambda: forecast_solar.collect_and_predict(
                    self.hass,
                    *_get_prediction_window(
                        datetime.now(ZoneInfo(self.config.timezone)),
                        PREDICT_DAYS_BACK,
                        PREDICT_DAYS_FORWARD,
                    ),
                ),
            ),
            PredictionTask(
                name="Consumption prediction",
                update_interval=timedelta(minutes=15),
                forecast_key=const.FORECAST_DATA_POWER_CONSUMPTION,
                predict_callable=lambda: forecast_consumption.generate_predictions(
                    self.hass,
                    *_get_prediction_window(
                        datetime.now(ZoneInfo(self.config.timezone)),
                        PREDICT_DAYS_BACK,
                        PREDICT_DAYS_FORWARD,
                    ),
                ),
            ),
            PredictionTask(
                name="Battery prediction",
                update_interval=timedelta(minutes=1),
                forecast_key=const.FORECAST_DATA_BATTERY,
                predict_callable=lambda: self.hass.async_add_executor_job(
                    forecast_battery.forecast_battery_capacity,
                    self.hass,
                    PREDICT_DAYS_FORWARD,
                    self.forecasts.get(const.FORECAST_DATA_PV_POWER),
                    self.forecasts.get(const.FORECAST_DATA_POWER_CONSUMPTION),
                ),
            ),
            PredictionTask(
                name="Grid prediction",
                update_interval=timedelta(minutes=1),
                forecast_key=const.FORECAST_DATA_GRID,
                predict_callable=lambda: self.hass.async_add_executor_job(
                    forecast_grid.forecast_grid,
                    self.hass,
                    PREDICT_DAYS_FORWARD,
                    self.forecasts.get(const.FORECAST_DATA_PV_POWER),
                    self.forecasts.get(const.FORECAST_DATA_POWER_CONSUMPTION),
                    self.forecasts.get(const.FORECAST_DATA_BATTERY),
                ),
            ),
        ]

    async def _async_update_data(self):
        """Run training and prediction tasks sequentially."""
        now = datetime.now(ZoneInfo(self.config.timezone))
        executed_forecasts: dict[str, ForecastData] = {}

        # Execute training tasks
        for task in self.training_tasks:
            if task.needs_training(now):
                try:
                    training_start = now - timedelta(days=60)
                    training_end = now - timedelta(hours=1)
                    await task.train_callable(self.hass, training_start, training_end)
                    _LOGGER.info("%s completed successfully", task.name)
                except Exception as e:
                    _LOGGER.error("Error during %s: %s", task.name, e)

        # Execute prediction tasks
        for task in self.prediction_tasks:
            if task.needs_update(now):
                try:
                    forecast_data: ForecastData = await task.predict_callable()

                    self.forecasts[task.forecast_key] = forecast_data
                    executed_forecasts[task.forecast_key] = forecast_data
                    task.mark_updated(now)
                    _LOGGER.info("%s completed successfully", task.name)
                except Exception as e:
                    if len(self.forecasts) != len(self.prediction_tasks):
                        _LOGGER.warning(
                            "Not all forecasts are done, raising config entry is not ready to try again later. Prediction: %s, Error: %s ",
                            task.name,
                            e,
                        )
                        raise ConfigEntryNotReady from e
                    _LOGGER.error("Error during %s: %s", task.name, e)

        return executed_forecasts
