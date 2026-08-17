"""Tests for the Income & Expenses view (P0.2).

Covers the reconciliation guarantee (category totals sum to the page
totals) and the deliberate separation between dataset-derived actuals and
the farmer's manual entry ledger (see services/income_expense_service.py
module docstring for why they are not merged).
"""

from __future__ import annotations

import pytest

import services.financial_record_service as record_svc
from services.dashboard_summary import get_selected_sector_data
from services.income_expense_service import build_income_expense_summary


@pytest.fixture(autouse=True)
def isolated_records_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(record_svc, "FINANCIAL_RECORDS_DIR", str(tmp_path))
    yield tmp_path


FARM = "multi_sector_farm.json"


def test_category_totals_reconcile_to_page_totals():
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    summary = build_income_expense_summary(FARM, ["dairy", "beef", "lamb"], filtered_raw=filtered)

    assert summary["income_total"] == round(sum(r["total"] for r in summary["income_categories"]), 2)
    assert summary["expense_total"] == round(sum(r["total"] for r in summary["expense_categories"]), 2)
    assert summary["difference"] == round(summary["income_total"] - summary["expense_total"], 2)


def test_grants_and_loan_repayments_appear_as_categories():
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    summary = build_income_expense_summary(FARM, ["dairy", "beef", "lamb"], filtered_raw=filtered)

    income_ids = {r["category_id"] for r in summary["income_categories"]}
    expense_ids = {r["category_id"] for r in summary["expense_categories"]}
    assert "grants_schemes" in income_ids
    assert "loan_repayments" in expense_ids


def test_category_choices_match_domain_vocabulary():
    filtered = get_selected_sector_data(FARM, ["dairy"])
    summary = build_income_expense_summary(FARM, ["dairy"], filtered_raw=filtered)
    income_ids = {c["id"] for c in summary["income_category_choices"]}
    expense_ids = {c["id"] for c in summary["expense_category_choices"]}
    assert "milk" in income_ids
    assert "feed" in expense_ids


def test_manual_entries_are_additive_not_merged_into_dataset_totals():
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    before = build_income_expense_summary(FARM, ["dairy", "beef", "lamb"], filtered_raw=filtered)

    record_svc.add_financial_record(FARM, {
        "record_type": "expense", "date": "2026-01-05", "category": "feed",
        "amount": 999.0, "description": "Extra feed", "counterparty": None,
        "notes": None, "sector": None,
    })

    after = build_income_expense_summary(FARM, ["dairy", "beef", "lamb"], filtered_raw=filtered)

    # The dataset-derived category totals must be completely unaffected by
    # a manual entry - the two sources stay separate until a reconciliation
    # policy is defined (P0.4), so no dataset-derived figure can double-count.
    assert after["income_total"] == before["income_total"]
    assert after["expense_total"] == before["expense_total"]
    assert after["expense_categories"] == before["expense_categories"]

    # The manual ledger's own totals do reflect the new entry.
    assert after["manual_expense_total"] == 999.0
    assert len(after["manual_records"]) == 1


def test_sector_filter_changes_totals():
    filtered_all = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    all_summary = build_income_expense_summary(FARM, ["dairy", "beef", "lamb"], filtered_raw=filtered_all)

    filtered_dairy = get_selected_sector_data(FARM, ["dairy"])
    dairy_summary = build_income_expense_summary(FARM, ["dairy"], filtered_raw=filtered_dairy)

    assert dairy_summary["income_total"] < all_summary["income_total"]
