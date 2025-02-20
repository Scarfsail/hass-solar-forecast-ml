from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .forecast_daily_summary import ForecastDailySummary


@dataclass
class ForecastData:
    """Type for storing forecast data with prediction timestamp."""

    forecast: list[dict[str, Any]]
    updated_at: datetime
    value_field_min: str
    value_field_med: str
    value_field_max: str
    daily_summaries: list[ForecastDailySummary] | None = None
    today_summary: ForecastDailySummary | None = None
