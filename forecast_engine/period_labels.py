"""Period-type metadata for dashboard/forecast figures (Phase 10 / UX item 3).

Every dashboard figure should say what time window it covers, so a farmer
never confuses a trailing-12-month actual with a forward forecast, a fixed
budget line, or a what-if scenario result. Dependency-free, like the other
``forecast_engine`` helper modules, so it can be imported anywhere.
"""

from __future__ import annotations

from datetime import date

HISTORICAL_ACTUAL = "Historical Actual"
TRAILING_12_MONTHS = "Trailing 12 Months"
CURRENT_YEAR_BUDGET = "Current-Year Budget"
FORECAST = "Forecast"
SCENARIO_RESULT = "Scenario Result"
POINT_IN_TIME = "Point in Time"

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def trailing_12_months(as_of: date | None = None) -> dict:
    """The rolling 12-month window ending today — used for revenue/profit/margin KPIs."""
    as_of = as_of or date.today()
    start = date(as_of.year - 1, as_of.month, 1)
    return {
        "period_type": TRAILING_12_MONTHS,
        "start_date": start.isoformat(),
        "end_date": as_of.isoformat(),
        "label": "Trailing 12 Months",
    }


def point_in_time(as_of: date | None = None) -> dict:
    """A single-instant figure, e.g. today's cash balance or debt outstanding."""
    as_of = as_of or date.today()
    return {
        "period_type": POINT_IN_TIME,
        "start_date": as_of.isoformat(),
        "end_date": as_of.isoformat(),
        "label": f"As of {as_of.isoformat()}",
    }


def forecast_window(months: int = 12, as_of: date | None = None) -> dict:
    """The forward-looking forecast window, e.g. the next 12 calendar months."""
    as_of = as_of or date.today()
    end_year = as_of.year + (as_of.month - 1 + months - 1) // 12
    end_month = (as_of.month - 1 + months - 1) % 12 + 1
    return {
        "period_type": FORECAST,
        "start_date": as_of.isoformat(),
        "end_date": date(end_year, end_month, 1).isoformat(),
        "label": f"Forecast — Next {months} Months",
    }


def _month_label(period: str) -> str:
    try:
        year_str, month_str = str(period).split("-")[:2]
        return f"{_MONTH_NAMES[int(month_str) - 1]} {year_str}"
    except (ValueError, IndexError, AttributeError, TypeError):
        return str(period)


def historical_month(period: str) -> dict:
    """A single named historical calendar month, e.g. '2024-03'."""
    return {
        "period_type": HISTORICAL_ACTUAL,
        "start_date": period,
        "end_date": period,
        "label": _month_label(period),
    }


def current_year_budget_month(period: str) -> dict:
    """A single budgeted (not-yet-actual) calendar month, e.g. '2025-06'."""
    meta = historical_month(period)
    meta["period_type"] = CURRENT_YEAR_BUDGET
    return meta


def scenario_result() -> dict:
    """A what-if scenario output — not tied to a specific calendar window."""
    return {
        "period_type": SCENARIO_RESULT,
        "start_date": None,
        "end_date": None,
        "label": "Scenario Result",
    }
