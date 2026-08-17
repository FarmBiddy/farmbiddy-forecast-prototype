"""Tests for multi-sector farm adapter."""

from __future__ import annotations

import pytest

from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from models.multi_sector_farm import MULTI_SECTOR_FILE
from services.multi_sector_farm import (
    aggregate_sector_financials,
    filter_farm_by_sectors,
    get_available_sectors,
    load_farm_for_analysis,
    load_multi_sector_farm,
    normalize_sectors,
    to_legacy_farm_dict,
)


@pytest.fixture
def farm():
    return load_multi_sector_farm(MULTI_SECTOR_FILE)


def test_load_multi_sector_farm(farm):
    assert farm["farm_name"] == "Knockrow Mixed Farm"
    assert len(get_available_sectors(farm)) == 3
    assert len(farm["sectors"]["dairy"]["monthly"]) == 24


def test_normalize_sectors_defaults(farm):
    assert normalize_sectors(None, farm) == ["dairy", "beef", "lamb"]


def test_beef_only_has_other_revenue(farm):
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["beef"])
    assert legacy["milking_cows"] == 0
    assert legacy["other_revenue"] > 0
    revenue = calculate_revenue(legacy)
    costs = calculate_costs(legacy)
    profit = calculate_profit(revenue, costs)
    assert revenue > 0
    assert profit == revenue - costs


def test_all_sectors_aggregate_higher_than_single(farm):
    dairy_only = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy"])
    all_sectors = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy", "beef", "lamb"])
    dairy_rev = calculate_revenue(dairy_only)
    all_rev = calculate_revenue(all_sectors)
    assert all_rev > dairy_rev


def test_trailing_twelve_monthly_forecast(farm):
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy", "beef", "lamb"])
    assert len(legacy["monthly_forecast"]) == 12
    assert legacy["monthly_forecast"][0]["month"] == 1


def test_kpi_visibility_hides_dairy_when_excluded(farm):
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["beef", "lamb"])
    assert legacy["kpi_visibility"]["revenue_per_cow"] is False
    assert legacy["kpi_visibility"]["beef"] is True


def test_aggregate_sector_financials_sums(farm):
    filtered = filter_farm_by_sectors(farm, ["dairy"])
    aggregated = aggregate_sector_financials(filtered)
    assert aggregated["revenue_totals"]["milk"] > 0
    legacy = to_legacy_farm_dict(aggregated, farm)
    assert legacy["feed"] > 0


def test_aggregate_sector_financials_keeps_per_lender_loans(farm):
    filtered = filter_farm_by_sectors(farm, ["dairy", "beef", "lamb"])
    aggregated = aggregate_sector_financials(filtered)
    assert len(aggregated["loans"]) == 2
    assert aggregated["loans"][0]["lender"] == "AIB Agri Finance"


def test_aggregate_sector_financials_builds_debt_register(farm):
    filtered = filter_farm_by_sectors(farm, ["dairy", "beef", "lamb"])
    aggregated = aggregate_sector_financials(filtered)
    register = aggregated["debt_register"]
    assert len(register) == 2
    for loan in register:
        assert loan["outstanding_balance"] >= 0
        assert loan["outstanding_balance"] <= loan["principal"]
        assert loan["years_remaining"] >= 0


def test_to_legacy_farm_dict_exposes_debt_register(farm):
    filtered = filter_farm_by_sectors(farm, ["dairy", "beef", "lamb"])
    aggregated = aggregate_sector_financials(filtered)
    legacy = to_legacy_farm_dict(aggregated, farm)
    assert legacy["debt_register"] == aggregated["debt_register"]
    assert legacy["_loans"] == aggregated["loans"]


def test_monthly_forecast_keeps_legacy_fields_unchanged(farm):
    """Farm/household split (Phase 2) must not alter the pre-existing figures."""
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy", "beef", "lamb"])
    for entry in legacy["monthly_forecast"]:
        assert entry["cashflow"] == round(entry["revenue"] - entry["costs"], 2)


def test_monthly_forecast_adds_household_and_combined_fields(farm):
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy", "beef", "lamb"])
    entry = legacy["monthly_forecast"][0]
    for key in (
        "farm_cashflow", "farm_running_balance",
        "household_income", "household_transfer_in", "household_outgoings",
        "household_net", "household_running_balance",
        "combined_cashflow", "combined_running_balance",
    ):
        assert key in entry


def test_combined_cashflow_nets_out_transfer_and_matches_legacy_plus_household(farm):
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy", "beef", "lamb"])
    for entry in legacy["monthly_forecast"]:
        expected_combined = round(
            entry["cashflow"] + entry["household_income"] - entry["household_outgoings"], 2
        )
        assert entry["combined_cashflow"] == expected_combined
        assert entry["farm_cashflow"] == round(entry["cashflow"] - entry["household_transfer_in"], 2)


def test_tax_month_increases_household_outgoings(farm):
    legacy = load_farm_for_analysis(MULTI_SECTOR_FILE, ["dairy", "beef", "lamb"])
    monthly = {e["month"]: e for e in legacy["monthly_forecast"]}
    tax_month = monthly[11]
    non_tax_month = monthly[10]
    assert tax_month["household_outgoings"] > non_tax_month["household_outgoings"]


def test_persisted_loans_overlay_dataset_loans_when_db_rows_exist(isolated_db):
    from repositories.loans import DbLoanRepository

    farm = load_multi_sector_farm(MULTI_SECTOR_FILE)
    assert farm["farm_summary"]["loans"][0]["lender"] == "AIB Agri Finance"

    DbLoanRepository().save(MULTI_SECTOR_FILE, [
        {"lender": "Demo Credit Union", "principal": 10000, "monthly_repayment": 200, "rate": 5.0, "maturity": "2028-01"},
    ])
    overlaid = load_multi_sector_farm(MULTI_SECTOR_FILE)
    loans = overlaid["farm_summary"]["loans"]
    assert len(loans) == 1
    assert loans[0]["lender"] == "Demo Credit Union"
    assert loans[0]["principal"] == pytest.approx(10000.0)
