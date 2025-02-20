from collections import defaultdict
from datetime import datetime

from .forecast_daily_summary import ForecastDailySummary
from .forecast_data import ForecastData


def aggregate_daily_forecast(forecast_data: ForecastData):
    """
    Given a ForecastData object (which contains a list of entries, each with a "time" and
    one or more value fields) aggregates the 'med' field by day. For each day, returns:
      - Minimum 'med' value and its time
      - Maximum 'med' value and its time
      - Average of 'med'
      - Sum of 'med'

    The name of the field to use is taken from forecast_data.value_field_med.
    """
    # Group entries by day (using the "time" field)
    grouped = defaultdict(list)
    for entry in forecast_data.forecast:
        # Get the timestamp. If it's a string, convert it.
        t = entry["time"]
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        day = t.date()
        # Extract the med value
        try:
            med_value = float(entry[forecast_data.value_field_med])
        except (KeyError, ValueError) as err:
            continue  # skip entries with missing or non-numeric med value
        # Store as tuple (timestamp, med_value)
        grouped[day].append((t, med_value))

    summaries: list[ForecastDailySummary] = []
    for day, values in grouped.items():
        if not values:
            continue
        # Find the entry with minimum med value
        min_entry = min(values, key=lambda x: x[1])
        # Find the entry with maximum med value
        max_entry = max(values, key=lambda x: x[1])
        # Compute sum and average
        total = sum(v for _, v in values)
        avg = total / len(values)
        summaries.append(
            ForecastDailySummary(
                date=day,
                med_min=min_entry[1],
                med_min_time=min_entry[0],
                med_max=max_entry[1],
                med_max_time=max_entry[0],
                med_avg=avg,
                med_sum=total,
            )
        )
    forecast_data.daily_summaries = summaries
    forecast_data.today_summary = next(
        (summary for summary in summaries if summary.date == datetime.now().date()),
        None,
    )
