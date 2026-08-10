"""Tests for short-term vs long-term/structural cash-flow classification (Teagasc item 3)."""

from __future__ import annotations

from forecast_engine.cashflow_classifier import (
    LONG_TERM,
    SHORT_TERM,
    classify_cashflow_entries,
    debt_to_revenue_ratio,
)


def _entry(status: str) -> dict:
    return {"cashflow_status": status}


def test_non_deficit_months_are_not_classified():
    entries = [_entry("surplus"), _entry("breakeven")]
    result = classify_cashflow_entries(entries)
    assert all(e["classification"] is None for e in result)
    assert all(e["classification_reason"] == "" for e in result)


def test_isolated_deficit_month_is_short_term():
    entries = [_entry("surplus"), _entry("deficit"), _entry("surplus"), _entry("surplus")]
    result = classify_cashflow_entries(entries)
    assert result[1]["classification"] == SHORT_TERM
    assert "isolated" in result[1]["classification_reason"].lower()


def test_persistent_run_of_deficits_is_long_term():
    entries = [_entry("deficit"), _entry("deficit"), _entry("deficit"), _entry("surplus")]
    result = classify_cashflow_entries(entries)
    assert result[0]["classification"] == LONG_TERM
    assert result[1]["classification"] == LONG_TERM
    assert result[2]["classification"] == LONG_TERM
    assert "3-month run" in result[0]["classification_reason"]


def test_short_run_below_threshold_stays_short_term():
    entries = [_entry("surplus"), _entry("deficit"), _entry("deficit"), _entry("surplus")]
    result = classify_cashflow_entries(entries)
    assert result[1]["classification"] == SHORT_TERM
    assert result[2]["classification"] == SHORT_TERM


def test_high_debt_forces_long_term_even_when_isolated():
    entries = [_entry("surplus"), _entry("deficit"), _entry("surplus")]
    debt_register = [{"outstanding_balance": 200000}]
    result = classify_cashflow_entries(entries, debt_register=debt_register, annual_revenue=100000)
    assert result[1]["classification"] == LONG_TERM
    assert "debt is high" in result[1]["classification_reason"]


def test_low_margin_forces_long_term():
    entries = [_entry("surplus"), _entry("deficit"), _entry("surplus")]
    result = classify_cashflow_entries(entries, profit_margin=-10.0)
    assert result[1]["classification"] == LONG_TERM
    assert "profit margin" in result[1]["classification_reason"]


def test_debt_to_revenue_ratio_basic():
    debt_register = [{"outstanding_balance": 50000}, {"outstanding_balance": 25000}]
    assert debt_to_revenue_ratio(debt_register, 75000) == 1.0
    assert debt_to_revenue_ratio(debt_register, 0) == 0.0
    assert debt_to_revenue_ratio(None, 100000) == 0.0
