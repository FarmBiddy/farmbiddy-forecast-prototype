"""Tests for category-level budget persistence (P0.3).

Every test points `CATEGORY_BUDGETS_DIR` at a pytest tmp_path so these
never touch the real outputs/farm_events/category_budgets/ storage.
"""

from __future__ import annotations

import pytest

import repositories.category_budgets as budgets_repo
import services.category_budget_service as svc


@pytest.fixture(autouse=True)
def isolated_budgets_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path))
    yield tmp_path


FARM = "test_farm.json"


def test_set_monthly_budget_creates_record():
    budget = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 450.0, "sector": None, "notes": None,
    })
    assert budget["id"]
    assert budget["source"] == "monthly"
    assert budget["amount"] == 450.0
    assert budget["annual_total"] is None
    assert budget["allocation_rule"] is None


def test_set_monthly_budget_twice_upserts_same_slot():
    first = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 450.0, "sector": None, "notes": None,
    })
    second = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 500.0, "sector": None, "notes": "Raised after quote",
    })
    assert second["id"] == first["id"]
    assert second["amount"] == 500.0
    assert second["notes"] == "Raised after quote"

    budgets = svc.list_category_budgets(FARM)
    assert len(budgets) == 1


def test_set_monthly_budget_rejects_unknown_category():
    with pytest.raises(ValueError):
        svc.set_monthly_budget(FARM, {
            "record_type": "expense", "category": "not_real", "year": 2026, "month": 3,
            "amount": 100.0, "sector": None, "notes": None,
        })


def test_set_annual_budget_creates_12_months_summing_exactly():
    created = svc.set_annual_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026,
        "annual_amount": 1000.0, "sector": None, "notes": None,
    })
    assert len(created) == 12
    assert {b["month"] for b in created} == set(range(1, 13))
    assert all(b["source"] == "annual_allocation" for b in created)
    assert all(b["allocation_rule"] == "even_12" for b in created)
    assert all(b["annual_total"] == 1000.0 for b in created)
    # The 12 monthly parts always sum exactly to the annual figure entered,
    # even though 1000 / 12 does not divide evenly.
    assert round(sum(b["amount"] for b in created), 2) == 1000.0


def test_set_annual_budget_uneven_split_has_no_fabricated_drift():
    created = svc.set_annual_budget(FARM, {
        "record_type": "income", "category": "milk", "year": 2026,
        "annual_amount": 100.0, "sector": None, "notes": None,
    })
    amounts = sorted(b["amount"] for b in created)
    # 11 months of 8.33 plus one month absorbing the remainder.
    assert amounts[0] == 8.33
    assert round(sum(amounts), 2) == 100.0


def test_set_annual_budget_then_monthly_upserts_same_slot():
    svc.set_annual_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026,
        "annual_amount": 1200.0, "sector": None, "notes": None,
    })
    # Farmer manually overrides March after the annual split.
    updated = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 999.0, "sector": None, "notes": "One-off higher feed month",
    })
    assert updated["source"] == "monthly"
    assert updated["amount"] == 999.0

    budgets = svc.list_category_budgets(FARM, record_type="expense", category="feed", year=2026)
    assert len(budgets) == 12
    march = next(b for b in budgets if b["month"] == 3)
    assert march["amount"] == 999.0
    assert march["source"] == "monthly"
    other_month = next(b for b in budgets if b["month"] == 4)
    assert other_month["source"] == "annual_allocation"


def test_update_category_budget_edits_amount_and_notes():
    budget = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 450.0, "sector": None, "notes": None,
    })
    updated = svc.update_category_budget(FARM, budget["id"], {"amount": 475.0, "notes": "Adjusted"})
    assert updated["amount"] == 475.0
    assert updated["notes"] == "Adjusted"


def test_update_category_budget_not_found_raises():
    with pytest.raises(svc.CategoryBudgetNotFoundError):
        svc.update_category_budget(FARM, "missing-id", {"amount": 10})


def test_delete_category_budget_removes_it():
    budget = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 450.0, "sector": None, "notes": None,
    })
    svc.delete_category_budget(FARM, budget["id"])
    assert svc.list_category_budgets(FARM) == []


def test_delete_category_budget_twice_raises_not_found():
    budget = svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 450.0, "sector": None, "notes": None,
    })
    svc.delete_category_budget(FARM, budget["id"])
    with pytest.raises(svc.CategoryBudgetNotFoundError):
        svc.delete_category_budget(FARM, budget["id"])


def test_list_category_budgets_filters_by_sector():
    svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 300.0, "sector": "dairy", "notes": None,
    })
    svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 150.0, "sector": "beef", "notes": None,
    })
    svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "fuel", "year": 2026, "month": 3,
        "amount": 90.0, "sector": None, "notes": None,
    })

    dairy_only = svc.list_category_budgets(FARM, sectors=["dairy"])
    assert len(dairy_only) == 2  # dairy-scoped budget + the sector-less whole-farm budget
    assert all(b.get("sector") in (None, "dairy") for b in dairy_only)


def test_budget_lookup_prefers_sector_specific_over_whole_farm():
    svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 1000.0, "sector": None, "notes": None,
    })
    svc.set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 400.0, "sector": "dairy", "notes": None,
    })

    resolved = svc.budget_lookup(FARM, sectors=["dairy"])
    key = ("expense", "feed", 2026, 3)
    assert resolved[key]["amount"] == 400.0
    assert resolved[key]["sector"] == "dairy"


def test_farms_are_isolated_from_each_other():
    svc.set_monthly_budget("farm_a.json", {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 3,
        "amount": 100.0, "sector": None, "notes": None,
    })
    svc.set_monthly_budget("farm_b.json", {
        "record_type": "income", "category": "milk", "year": 2026, "month": 3,
        "amount": 200.0, "sector": None, "notes": None,
    })
    assert len(svc.list_category_budgets("farm_a.json")) == 1
    assert len(svc.list_category_budgets("farm_b.json")) == 1
