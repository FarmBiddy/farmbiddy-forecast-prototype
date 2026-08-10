"""Tests for the Phase 9 lightweight data-quality checks."""

from datetime import date

from forecast_engine.data_quality import (
    build_data_quality_warnings,
    check_data_freshness,
    check_loan_assumptions,
    check_missing_required_fields,
    check_revenue_reconciliation,
    check_sample_data,
)


def test_check_data_freshness_recent_data_has_no_warning():
    assert check_data_freshness("2026-06", today=date(2026, 7, 20)) == []


def test_check_data_freshness_slightly_stale_data_flags_medium():
    warnings = check_data_freshness("2026-04", today=date(2026, 7, 20))
    assert len(warnings) == 1
    assert warnings[0]["type"] == "outdated_data"
    assert warnings[0]["severity"] == "medium"
    assert "2026-04" in warnings[0]["message"]


def test_check_data_freshness_very_stale_data_flags_high():
    warnings = check_data_freshness("2025-01", today=date(2026, 7, 20))
    assert warnings[0]["severity"] == "high"


def test_check_data_freshness_missing_period_flags_missing_data():
    warnings = check_data_freshness(None)
    assert warnings[0]["type"] == "missing_data"


def test_check_missing_required_fields_flags_absent_fields():
    warnings = check_missing_required_fields({"milk_price": 0.42})
    assert any(w["area"] == "Cash Available" for w in warnings)
    assert not any(w["area"] == "Milk Price" for w in warnings)


def test_check_missing_required_fields_none_when_present():
    warnings = check_missing_required_fields({"opening_cash_balance": 5000, "milk_price": 0.42})
    assert warnings == []


def test_check_loan_assumptions_flags_missing_rate_or_maturity():
    debt_register = [{"lender": "Bank A", "outstanding_balance": 1000}]
    raw_loans = [{"lender": "Bank A", "principal": 10000, "monthly_repayment": 200}]
    warnings = check_loan_assumptions(debt_register, raw_loans)
    assert len(warnings) == 1
    assert "Bank A" in warnings[0]["message"]
    assert "rate" in warnings[0]["message"] or "maturity" in warnings[0]["message"]


def test_check_loan_assumptions_no_warning_when_complete():
    debt_register = [{"lender": "Bank A", "outstanding_balance": 1000}]
    raw_loans = [{
        "lender": "Bank A", "principal": 10000, "monthly_repayment": 200,
        "rate": 5.5, "maturity": "2030-01",
    }]
    assert check_loan_assumptions(debt_register, raw_loans) == []


def test_check_revenue_reconciliation_flags_large_mismatch():
    forecast_summary = {"annual_revenue": 200000}
    monthly_forecast = [{"revenue": 5000} for _ in range(12)]  # sums to 60000
    warnings = check_revenue_reconciliation(forecast_summary, monthly_forecast)
    assert len(warnings) == 1
    assert warnings[0]["type"] == "reconciliation"


def test_check_revenue_reconciliation_no_warning_within_tolerance():
    forecast_summary = {"annual_revenue": 60000}
    monthly_forecast = [{"revenue": 5000} for _ in range(12)]  # sums to 60000
    assert check_revenue_reconciliation(forecast_summary, monthly_forecast) == []


def test_check_sample_data_flags_when_marked():
    assert check_sample_data({"is_sample_data": True})[0]["type"] == "sample_data"


def test_check_sample_data_no_warning_when_not_marked():
    assert check_sample_data({"is_sample_data": False}) == []
    assert check_sample_data({}) == []
    assert check_sample_data(None) == []


def test_build_data_quality_warnings_combines_all_checks():
    warnings = build_data_quality_warnings(
        farm={"opening_cash_balance": None, "milk_price": 0.42, "_loans": []},
        profile={"is_sample_data": True},
        forecast_summary={"annual_revenue": 0},
        monthly_forecast=[],
        debt_register=[],
        latest_period="2025-12",
        today=date(2026, 7, 20),
    )
    types = {w["type"] for w in warnings}
    assert "sample_data" in types
    assert "outdated_data" in types
    assert "missing_data" in types
