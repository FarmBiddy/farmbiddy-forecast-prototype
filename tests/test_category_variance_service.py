"""Tests for category-level Budget vs Actual (P0.3).

Uses the real `multi_sector_farm.json` dataset (its trailing-12-month
window is 2025-01..2025-12, see services/income_expense_service.py) so
Actuals come from genuine dataset figures, not fabricated test data.
Budget/records storage is isolated to tmp_path.
"""

from __future__ import annotations

import pytest

import services.category_budget_service as budget_svc
import services.financial_record_service as record_svc
from services.category_variance_service import build_category_budget_vs_actual
from services.dashboard_summary import get_selected_sector_data
from services.income_expense_service import dataset_monthly_category_totals

FARM = "multi_sector_farm.json"
SECTORS = ["dairy", "beef", "lamb"]


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(budget_svc, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    monkeypatch.setattr(record_svc, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    yield tmp_path


@pytest.fixture()
def filtered():
    return get_selected_sector_data(FARM, SECTORS)


def test_no_budgets_set_returns_no_budget_set_state(filtered):
    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    assert result["overall_status"] == "no_budget_set"
    assert result["overall_budget_total"] is None
    assert result["categories"] == []
    assert len(result["unbudgeted_categories"]) > 0
    assert all(row["status"] == "no_budget_set" for row in result["unbudgeted_categories"])
    # Never a fabricated zero variance for an unbudgeted category.
    assert all(row["difference"] is None for row in result["unbudgeted_categories"])


def test_missing_budget_never_shows_zero_variance_for_a_real_category(filtered):
    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    feed_row = next(r for r in result["unbudgeted_categories"] if r["category_id"] == "feed")
    assert feed_row["status"] == "no_budget_set"
    assert feed_row["budget_total"] is None
    assert feed_row["actual_total"] is None


def test_budget_matching_actual_is_on_budget(filtered):
    totals = dataset_monthly_category_totals(filtered, months=12)
    for year, month in [(y, m) for (y, m, rt, cat) in totals if rt == "expense" and cat == "feed"]:
        amount = totals[(year, month, "expense", "feed")]
        budget_svc.set_monthly_budget(FARM, {
            "record_type": "expense", "category": "feed", "year": year, "month": month,
            "amount": amount, "sector": None, "notes": None,
        })

    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    feed_row = next(r for r in result["categories"] if r["category_id"] == "feed")
    assert feed_row["status"] == "on_budget"
    assert feed_row["difference"] == 0.0
    assert feed_row["months_with_budget"] == feed_row["months_in_window"]


def test_budget_below_actual_expense_is_above_budget(filtered):
    totals = dataset_monthly_category_totals(filtered, months=12)
    feed_months = [(y, m) for (y, m, rt, cat) in totals if rt == "expense" and cat == "feed"]
    for year, month in feed_months:
        actual = totals[(year, month, "expense", "feed")]
        # A clearly-material shortfall (well beyond the comparison's
        # tolerance band) so this is unambiguously "above budget", not a
        # rounding-level difference.
        budget_svc.set_monthly_budget(FARM, {
            "record_type": "expense", "category": "feed", "year": year, "month": month,
            "amount": max(actual * 0.5, 0), "sector": None, "notes": None,
        })

    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    feed_row = next(r for r in result["categories"] if r["category_id"] == "feed")
    assert feed_row["status"] == "above_budget"
    assert feed_row["difference"] > 0
    assert "above budget" in feed_row["summary"]
    assert feed_row in result["top_contributors"]


def test_reconciliation_categories_plus_unbudgeted_cover_all_seen_categories(filtered):
    totals = dataset_monthly_category_totals(filtered, months=12)
    feed_months = [(y, m) for (y, m, rt, cat) in totals if rt == "expense" and cat == "feed"]
    for year, month in feed_months[:3]:
        budget_svc.set_monthly_budget(FARM, {
            "record_type": "expense", "category": "feed", "year": year, "month": month,
            "amount": 100.0, "sector": None, "notes": None,
        })

    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    feed_row = next(r for r in result["categories"] if r["category_id"] == "feed")
    # Only the 3 months actually budgeted count toward this category's comparison.
    assert feed_row["months_with_budget"] == 3
    assert feed_row["budget_total"] == 300.0

    all_seen_ids = {(r["record_type"], r["category_id"]) for r in result["categories"] + result["unbudgeted_categories"]}
    assert ("expense", "feed") in all_seen_ids
    assert ("income", "milk") in all_seen_ids  # never disappears just because it's unbudgeted


def test_manual_records_feed_into_actuals_for_budgeted_category(filtered):
    # A category with no dataset-derived actual at all — only manual entries —
    # must still be comparable once a budget exists for it.
    record_svc.add_financial_record(FARM, {
        "record_type": "expense", "date": "2025-06-15", "category": "insurance",
        "amount": 500.0, "description": "Top-up policy", "counterparty": None,
        "notes": None, "sector": None,
    })
    budget_svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "insurance", "year": 2025, "month": 6,
        "amount": 500.0, "sector": None, "notes": None,
    })

    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    insurance_row = next(r for r in result["categories"] if r["category_id"] == "insurance")
    # Dataset already has some insurance cost in June; the manual EUR500 must
    # be additive on top of it, not silently dropped or replacing it.
    dataset_june_insurance = dataset_monthly_category_totals(filtered, months=12).get((2025, 6, "expense", "insurance"), 0.0)
    assert insurance_row["actual_total"] == round(dataset_june_insurance + 500.0, 2)


def test_overall_summary_reflects_status(filtered):
    result_none = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    assert result_none["overall_status"] == "no_budget_set"

    totals = dataset_monthly_category_totals(filtered, months=12)
    for (year, month, rt, cat), amount in totals.items():
        if rt == "expense" and cat == "feed":
            budget_svc.set_monthly_budget(FARM, {
                "record_type": "expense", "category": "feed", "year": year, "month": month,
                "amount": amount, "sector": None, "notes": None,
            })

    result = build_category_budget_vs_actual(FARM, SECTORS, filtered_raw=filtered)
    assert result["overall_status"] == "on_budget"
    assert result["overall_difference"] == 0.0
