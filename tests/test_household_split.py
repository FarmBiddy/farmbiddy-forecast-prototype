"""Tests for the farm/household cash-movement split (Teagasc item 5)."""

from __future__ import annotations

from models.multi_sector_farm import compute_household_month


def test_compute_household_month_non_tax_month():
    household = {
        "drawings_monthly": 2000,
        "off_farm_income_monthly": 500,
        "pension_insurance_monthly": 200,
        "farm_to_household_transfer_monthly": 1800,
        "tax_annual": 6000,
        "tax_payment_months": [11],
    }
    result = compute_household_month(household, 6)
    assert result["income"] == 500
    assert result["transfer_in"] == 1800
    assert result["outgoings"] == 2200
    assert result["net"] == 500 + 1800 - 2200


def test_compute_household_month_tax_month_adds_lump_sum():
    household = {
        "drawings_monthly": 2000,
        "off_farm_income_monthly": 500,
        "pension_insurance_monthly": 200,
        "farm_to_household_transfer_monthly": 1800,
        "tax_annual": 6000,
        "tax_payment_months": [11],
    }
    result = compute_household_month(household, 11)
    assert result["outgoings"] == 2200 + 6000


def test_compute_household_month_splits_tax_across_multiple_months():
    household = {"tax_annual": 4000, "tax_payment_months": [5, 11]}
    may = compute_household_month(household, 5)
    november = compute_household_month(household, 11)
    other = compute_household_month(household, 6)
    assert may["outgoings"] == 2000
    assert november["outgoings"] == 2000
    assert other["outgoings"] == 0


def test_compute_household_month_handles_missing_block():
    result = compute_household_month(None, 3)
    assert result == {"income": 0, "transfer_in": 0, "outgoings": 0, "net": 0}


def test_compute_household_month_handles_empty_dict():
    result = compute_household_month({}, 1)
    assert result["net"] == 0
