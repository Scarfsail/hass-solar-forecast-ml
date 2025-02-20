from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ForecastDailySummary:
    """Aggregated forecast summary for one day."""

    date: date
    med_min: float
    med_min_time: datetime
    med_max: float
    med_max_time: datetime
    med_avg: float
    med_sum: float
