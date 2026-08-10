"""Tests for the Phase 10 period-type metadata helpers."""

from datetime import date

from forecast_engine.period_labels import (
    CURRENT_YEAR_BUDGET,
    FORECAST,
    HISTORICAL_ACTUAL,
    POINT_IN_TIME,
    SCENARIO_RESULT,
    TRAILING_12_MONTHS,
    current_year_budget_month,
    forecast_window,
    historical_month,
    point_in_time,
    scenario_result,
    trailing_12_months,
)


def test_trailing_12_months_spans_one_year_ending_today():
    meta = trailing_12_months(date(2026, 7, 20))
    assert meta["period_type"] == TRAILING_12_MONTHS
    assert meta["start_date"] == "2025-07-01"
    assert meta["end_date"] == "2026-07-20"
    assert meta["label"]


def test_point_in_time_is_a_single_date():
    meta = point_in_time(date(2026, 7, 20))
    assert meta["period_type"] == POINT_IN_TIME
    assert meta["start_date"] == meta["end_date"] == "2026-07-20"


def test_forecast_window_spans_requested_months():
    meta = forecast_window(12, date(2026, 7, 20))
    assert meta["period_type"] == FORECAST
    assert meta["start_date"] == "2026-07-20"
    assert meta["end_date"] == "2027-06-01"


def test_forecast_window_handles_year_rollover():
    meta = forecast_window(6, date(2026, 12, 1))
    assert meta["end_date"].startswith("2027-")


def test_historical_month_labels_calendar_month():
    meta = historical_month("2025-03")
    assert meta["period_type"] == HISTORICAL_ACTUAL
    assert meta["label"] == "Mar 2025"
    assert meta["start_date"] == meta["end_date"] == "2025-03"


def test_historical_month_falls_back_gracefully_on_bad_input():
    meta = historical_month("not-a-period")
    assert meta["label"] == "not-a-period"


def test_current_year_budget_month_reuses_historical_label_logic():
    meta = current_year_budget_month("2025-06")
    assert meta["period_type"] == CURRENT_YEAR_BUDGET
    assert meta["label"] == "Jun 2025"


def test_scenario_result_has_no_calendar_dates():
    meta = scenario_result()
    assert meta["period_type"] == SCENARIO_RESULT
    assert meta["start_date"] is None
    assert meta["end_date"] is None
