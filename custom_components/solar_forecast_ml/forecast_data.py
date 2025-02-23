from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, List, Literal, Optional, TypeVar, Union
from zoneinfo import ZoneInfo

from . import config

T = TypeVar("T", bound=int | float)


@dataclass
class ForecastData:
    """Type for storing forecast data with prediction timestamp."""

    forecast: list[dict[str, Any]]
    updated_at: datetime
    value_field_min: str
    value_field_med: str
    value_field_max: str

    def get_forecast_records_for_rest_of_today(self):
        now = datetime.now(ZoneInfo(config.Configuration.get_instance().timezone))
        today = now.date()

        return (
            point[self.value_field_med]
            for point in self.forecast
            if (point_time := datetime.fromisoformat(point["time"])) > now
            and point_time.date() == today
        )

    def get_forecast_records_for_today(self):
        now = datetime.now(ZoneInfo(config.Configuration.get_instance().timezone))
        today = now.date()

        return (
            point[self.value_field_med]
            for point in self.forecast
            if datetime.fromisoformat(point["time"]).date() == today
        )

    def get_nearest_forecast_record(self):
        now = datetime.now(ZoneInfo(config.Configuration.get_instance().timezone))

        last_past_point = None
        for point in self.forecast:
            point_time = datetime.fromisoformat(point["time"])
            if point_time > now:
                break
            last_past_point = point

        return last_past_point[self.value_field_med] if last_past_point else None

    def aggregate_by_interval(
        self,
        aggregation_fn: Literal["sum", "average"],
        post_process_fn: Optional[Callable[[float], float]] = None,
        interval: timedelta = timedelta(days=1),
    ) -> list[dict]:
        """Aggregate forecast data by interval for all value fields.

        Args:
            aggregation_fn: The aggregation function to use ("sum" or "average")
            post_process_fn: Optional function to process the aggregated value
            interval: Time interval for aggregation (default: 1 day)
            timezone: Timezone for aggregation (default: UTC)

        Returns:
            List of dictionaries containing aggregated values

        Raises:
            ValueError: If aggregation_fn is not "sum" or "average"
        """
        if aggregation_fn not in ["sum", "average"]:
            raise ValueError('aggregation_fn must be either "sum" or "average"')

        if not self.forecast:
            return []

        tz = ZoneInfo(config.Configuration.get_instance().timezone)
        result = []

        # Group data points by interval
        current_interval = {}
        interval_start = None
        points_in_interval = 0

        for point in self.forecast:
            point_time = datetime.fromisoformat(point["time"])
            if interval_start is None:
                interval_start = point_time

            # Check if we're still in the current interval
            if point_time - interval_start < interval:
                for field in [
                    self.value_field_min,
                    self.value_field_med,
                    self.value_field_max,
                ]:
                    if field is not None and field in point:  # Add null check
                        current_interval.setdefault(field, 0.0)
                        current_interval[field] += point[field]
                points_in_interval += 1
            else:
                # Process the completed interval
                interval_mid = interval_start + interval / 2
                interval_mid = datetime.combine(
                    interval_mid.date(), time(12, 0), tzinfo=tz
                )

                aggregated = {"time": interval_mid.isoformat()}

                # Calculate aggregated values for each field
                for field in [
                    self.value_field_min,
                    self.value_field_med,
                    self.value_field_max,
                ]:
                    if (
                        field is not None and field in current_interval
                    ):  # Add null check
                        value = current_interval[field]
                        if aggregation_fn == "average":
                            value = value / points_in_interval
                        elif aggregation_fn == "sum":
                            value = value

                        if post_process_fn:
                            value = post_process_fn(value)

                        aggregated[field] = value

                result.append(aggregated)

                # Start new interval
                interval_start = point_time
                current_interval = {
                    field: point[field]
                    for field in [
                        self.value_field_min,
                        self.value_field_med,
                        self.value_field_max,
                    ]
                    if field is not None and field in point  # Add null check
                }
                points_in_interval = 1

        # Process the last interval if it contains data
        if current_interval and points_in_interval > 0:
            interval_mid = interval_start + interval / 2
            interval_mid = datetime.combine(interval_mid.date(), time(12, 0), tzinfo=tz)

            aggregated = {"time": interval_mid.isoformat()}

            for field in [
                self.value_field_min,
                self.value_field_med,
                self.value_field_max,
            ]:
                if field is not None and field in current_interval:  # Add null check
                    value = current_interval[field]
                    if aggregation_fn == "average":
                        value = value / points_in_interval
                    elif aggregation_fn == "sum":
                        value = value

                    if post_process_fn:
                        value = post_process_fn(value)

                    aggregated[field] = value

            result.append(aggregated)

        return result
