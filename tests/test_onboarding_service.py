"""Tests for Simple Farmer Onboarding (P1.3): category budgets created,
loan repayments combined without silent overwrite, current_cash/farm_type
overrides, and their propagation into to_legacy_farm_dict.
"""

from __future__ import annotations

import pytest

import repositories.category_budgets as budgets_repo
import repositories.onboarding as onboarding_repo
import services.category_budget_service as budget_svc
import services.onboarding_service as onboarding_svc
from services.multi_sector_farm import to_legacy_farm_dict

FARM = "test_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_repo, "ONBOARDING_DIR", str(tmp_path / "onboarding"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    yield tmp_path


def _request(**overrides):
    data = {
        "farm_type": "dairy",
        "income_items": [{"category": "milk", "annual_amount": 120000}],
        "cost_items": [{"category": "feed", "annual_amount": 30000}],
        "loan_items": [{"lender": "Bank", "monthly_repayment": 500, "outstanding_balance": 20000}],
        "current_cash": 15000,
        "year": 2026,
    }
    data.update(overrides)
    return data


def test_status_before_completion_is_not_completed():
    status = onboarding_svc.get_onboarding_status(FARM)
    assert status["completed"] is False
    assert status["farm_type"] is None
    assert len(status["farm_types"]) == 7
    assert any(c["id"] == "milk" for c in status["income_category_choices"])


def test_complete_onboarding_sets_income_and_cost_budgets():
    summary = onboarding_svc.complete_onboarding(FARM, _request())

    assert summary["farm_type"] == "dairy"
    assert summary["farm_type_label"] == "Dairy"
    assert summary["selected_sectors"] == ["dairy"]
    assert summary["income_budgets_set"] == 1
    # feed + combined loan repayments
    assert summary["cost_budgets_set"] == 2
    assert summary["loan_repayments_annual"] == pytest.approx(6000.0)
    assert summary["total_annual_income_budgeted"] == pytest.approx(120000.0)
    assert summary["total_annual_cost_budgeted"] == pytest.approx(30000.0 + 6000.0)
    assert summary["naive_annual_net"] == pytest.approx(120000.0 - 36000.0)
    assert summary["current_cash_set"] is True
    assert summary["current_cash"] == pytest.approx(15000.0)

    budgets = budget_svc.list_category_budgets(FARM, year=2026)
    milk_budgets = [b for b in budgets if b["category"] == "milk"]
    assert len(milk_budgets) == 12
    assert sum(b["amount"] for b in milk_budgets) == pytest.approx(120000.0)

    loan_budgets = [b for b in budgets if b["category"] == "loan_repayments"]
    assert len(loan_budgets) == 12
    assert sum(b["amount"] for b in loan_budgets) == pytest.approx(6000.0)
    assert loan_budgets[0]["annual_total"] == pytest.approx(6000.0)


def test_loan_items_and_explicit_loan_cost_item_combine_without_overwrite():
    request = _request(
        cost_items=[
            {"category": "feed", "annual_amount": 30000},
            {"category": "loan_repayments", "annual_amount": 1000},
        ],
        loan_items=[{"lender": "Bank", "monthly_repayment": 500, "outstanding_balance": None}],
    )
    summary = onboarding_svc.complete_onboarding(FARM, request)

    # 500*12 from loan_items + 1000 explicit cost item = 7000, not one
    # silently overwriting the other.
    assert summary["loan_repayments_annual"] == pytest.approx(7000.0)

    budgets = budget_svc.list_category_budgets(FARM, year=2026)
    loan_budgets = [b for b in budgets if b["category"] == "loan_repayments"]
    assert len(loan_budgets) == 12
    assert sum(b["amount"] for b in loan_budgets) == pytest.approx(7000.0)


def test_zero_amount_items_are_skipped():
    request = _request(
        income_items=[{"category": "milk", "annual_amount": 0}],
        cost_items=[{"category": "feed", "annual_amount": 0}],
        loan_items=[],
    )
    summary = onboarding_svc.complete_onboarding(FARM, request)

    assert summary["income_budgets_set"] == 0
    assert summary["cost_budgets_set"] == 0
    assert summary["loan_repayments_annual"] == 0
    budgets = budget_svc.list_category_budgets(FARM, year=2026)
    assert budgets == []


def test_completing_onboarding_persists_sectors_onto_the_farm_row_when_db_backed(isolated_db, monkeypatch):
    """P3.6: onboarding for a brand new farm (no pre-existing dataset) sets
    real, persisted Farm configuration - not just a read-time override."""
    monkeypatch.setenv("PERSISTENCE_BACKEND", "db")
    new_farm = "brand_new_onboarding_farm.json"

    onboarding_svc.complete_onboarding(new_farm, _request(farm_type="dairy"))

    from db.session import session_scope
    from identity.seed import get_or_create_farm

    with session_scope() as session:
        farm = get_or_create_farm(session, new_farm)
        assert farm.sectors == ["dairy"]
        assert farm.settings["farm_type"] == "dairy"
        assert farm.settings["farm_type_label"] == "Dairy"


def test_status_reflects_completed_onboarding():
    onboarding_svc.complete_onboarding(FARM, _request())
    status = onboarding_svc.get_onboarding_status(FARM)

    assert status["completed"] is True
    assert status["completed_at"] is not None
    assert status["farm_type"] == "dairy"
    assert status["farm_type_label"] == "Dairy"
    assert status["current_cash"] == pytest.approx(15000.0)
    assert status["loan_repayments_annual"] == pytest.approx(6000.0)


def test_current_cash_and_farm_type_override_flow_into_legacy_farm_dict():
    onboarding_svc.complete_onboarding(FARM, _request(current_cash=42000, farm_type="beef"))

    aggregated = {"cost_totals": {}, "selected_sectors": ["dairy"], "dairy": {}}
    raw_farm = {"farm_name": "Test Farm", "farm_summary": {"opening_cash_balance": 999.0}}

    legacy_without_override = to_legacy_farm_dict(aggregated, raw_farm)
    assert legacy_without_override["opening_cash_balance"] == pytest.approx(999.0)
    assert legacy_without_override["farm_type"] == "Mixed"

    legacy_with_override = to_legacy_farm_dict(aggregated, raw_farm, farm_file=FARM)
    assert legacy_with_override["opening_cash_balance"] == pytest.approx(42000.0)
    assert legacy_with_override["farm_type"] == "Beef"


def test_no_current_cash_leaves_opening_cash_balance_untouched():
    onboarding_svc.complete_onboarding(FARM, _request(current_cash=None))

    aggregated = {"cost_totals": {}, "selected_sectors": ["dairy"], "dairy": {}}
    raw_farm = {"farm_name": "Test Farm", "farm_summary": {"opening_cash_balance": 500.0}}

    legacy = to_legacy_farm_dict(aggregated, raw_farm, farm_file=FARM)
    assert legacy["opening_cash_balance"] == pytest.approx(500.0)


def test_unmodeled_farm_type_has_no_sector_mapping():
    summary = onboarding_svc.complete_onboarding(FARM, _request(farm_type="tillage"))
    assert summary["selected_sectors"] == []


def test_invalid_income_category_rejected_by_service():
    with pytest.raises(ValueError):
        onboarding_svc.complete_onboarding(
            FARM, _request(income_items=[{"category": "not_a_real_category", "annual_amount": 100}]),
        )
