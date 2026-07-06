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
