from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ForecastData:
    """Type for storing forecast data with prediction timestamp."""

    forecast: list[dict[str, Any]]
    updated_at: datetime
    value_field_min: str
    value_field_med: str
    value_field_max: str
