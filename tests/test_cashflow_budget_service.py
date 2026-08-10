"""Tests for monthly cash-flow budget vs. actual comparison (Teagasc items 1-2)."""

from __future__ import annotations

from services.cashflow_budget_service import (
    AHEAD,
    BEHIND,
    BREAKEVEN,
    DEFICIT,
    ON_BUDGET,
    SURPLUS,
    _cause_summary,
    compare_budget_vs_actual,
    compute_actual_cash_flow,
    get_budget_entries,
)
from services.dashboard_summary import get_selected_sector_data


def test_get_budget_entries_sorted_and_present():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    entries = get_budget_entries(filtered)
    assert len(entries) == 24
    periods = [e["period"] for e in entries]
    assert periods == sorted(periods)


def test_compute_actual_cash_flow_includes_scheme_payment_month():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    farm_summary = filtered.get("farm_summary") or {}
    actual = compute_actual_cash_flow(filtered, farm_summary, months=24)
    # BISS lands in month 10 for every year in this dataset.
    october_2024 = actual[(2024, 10)]
    september_2024 = actual[(2024, 9)]
    assert october_2024["actual_cash_in"] > september_2024["actual_cash_in"]


def test_compare_budget_vs_actual_baseline_year_is_on_budget():
    result = compare_budget_vs_actual("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    assert result["success"] is True
    baseline_entries = [e for e in result["entries"] if e["year"] == 2024]
    assert len(baseline_entries) == 12
    assert all(e["budget_status"] == ON_BUDGET for e in baseline_entries)


def test_compare_budget_vs_actual_counts_and_shape():
    result = compare_budget_vs_actual("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    assert len(result["entries"]) == 24
    assert result["deficit_months"] >= 0
    assert result["behind_budget_months"] >= 0
    entry = result["entries"][0]
    for key in (
        "period", "actual_cash_in", "actual_cash_out", "actual_net",
        "budgeted_cash_in", "budgeted_cash_out", "budgeted_net",
        "variance", "cashflow_status", "budget_status", "cause_summary",
    ):
        assert key in entry
    assert entry["cashflow_status"] in (DEFICIT, SURPLUS, BREAKEVEN)
    assert entry["budget_status"] in (AHEAD, BEHIND, ON_BUDGET)


def test_compare_budget_vs_actual_beef_only_still_returns_entries():
    result = compare_budget_vs_actual("multi_sector_farm.json", ["beef"])
    assert result["selected_sectors"] == ["beef"]
    assert len(result["entries"]) == 24


def test_cause_summary_on_budget_within_tolerance():
    summary = _cause_summary(cash_in_variance=10, cash_out_variance=5, net_variance=15, tolerance=50)
    assert summary.startswith("On budget")


def test_cause_summary_behind_due_to_cash_out():
    summary = _cause_summary(cash_in_variance=0, cash_out_variance=-2000, net_variance=-2000, tolerance=50)
    assert summary.startswith("Behind budget")
    assert "costs came in higher than budgeted" in summary


def test_cause_summary_ahead_due_to_cash_in():
    summary = _cause_summary(cash_in_variance=3000, cash_out_variance=0, net_variance=3000, tolerance=50)
    assert summary.startswith("Ahead of budget")
    assert "cash in was stronger than budgeted" in summary
