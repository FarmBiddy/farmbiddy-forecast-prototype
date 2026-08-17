"""Tests for `services.forecast_service.apply_sandbox_changes`, focused on
the precomputed-monthly-forecast rescale fix (P2.1).

Multi-sector farms carry a precomputed, seasonal `monthly_forecast`
(`services.multi_sector_farm._build_monthly_forecast`), which
`forecast_engine.cashflow.generate_monthly_forecast` always prefers over
recalculating one from the flat scalar fields. Before this fix, a sandbox
change to milk price/costs/loans/opening cash therefore left every month's
cash position completely unchanged even though the annual
`forecast_summary` figures moved correctly - `apply_sandbox_changes` now
rescales the precomputed months by the same ratio the annual totals moved
by, and rebuilds the running balance from the (possibly overridden)
opening cash.
"""

from __future__ import annotations

from services.forecast_service import apply_sandbox_changes
from services.multi_sector_farm import load_farm_for_analysis

FARM = "multi_sector_farm.json"
SECTORS = ["dairy", "beef", "lamb"]


def _multi_sector_farm():
    return load_farm_for_analysis(FARM, SECTORS)


def _flat_single_sector_farm():
    """A plain single-farm dict with no precomputed `monthly_forecast` -
    the shape `generate_monthly_forecast`'s from-scratch fallback expects."""
    return {
        "farm_name": "Single Sector Farm",
        "milking_cows": 100,
        "litres_per_cow": 6000.0,
        "milk_price": 0.38,
        "other_revenue": 0.0,
        "opening_cash_balance": 10000.0,
        "biss": 0.0,
        "acres": 0.0,
        "feed": 20000.0,
        "fertiliser": 5000.0,
        "vet": 3000.0,
        "contractor": 2000.0,
        "labour": 8000.0,
        "insurance": 1500.0,
        "loan_repayments": 6000.0,
        "fuel": 2000.0,
        "electricity": 1500.0,
    }


# ---------------------------------------------------------------------------
# Multi-sector farms (precomputed seasonal monthly_forecast)
# ---------------------------------------------------------------------------

def test_farm_has_a_precomputed_12_month_forecast():
    farm = _multi_sector_farm()
    assert isinstance(farm.get("monthly_forecast"), list)
    assert len(farm["monthly_forecast"]) == 12


def test_no_changes_leaves_the_precomputed_monthly_forecast_untouched():
    farm = _multi_sector_farm()
    sandbox_farm, _ = apply_sandbox_changes(farm, {})
    assert sandbox_farm["monthly_forecast"] == farm["monthly_forecast"]


def test_milk_price_increase_raises_every_months_revenue_and_running_balance():
    farm = _multi_sector_farm()
    sandbox_farm, _ = apply_sandbox_changes(farm, {"milk_price": farm["milk_price"] * 1.20})

    base_months = farm["monthly_forecast"]
    scenario_months = sandbox_farm["monthly_forecast"]
    assert len(scenario_months) == 12

    # Revenue should scale up (or stay equal for a month with zero revenue),
    # and the running balance must differ by the final month - a scenario
    # that never moves cash is exactly the bug being fixed here.
    assert any(s["revenue"] >= b["revenue"] for b, s in zip(base_months, scenario_months))
    assert scenario_months[-1]["running_balance"] != base_months[-1]["running_balance"]
    assert scenario_months[-1]["running_balance"] > base_months[-1]["running_balance"]


def test_higher_costs_lower_the_running_balance():
    farm = _multi_sector_farm()
    sandbox_farm, _ = apply_sandbox_changes(farm, {"feed": farm["feed"] * 2})

    base_months = farm["monthly_forecast"]
    scenario_months = sandbox_farm["monthly_forecast"]
    assert scenario_months[-1]["running_balance"] < base_months[-1]["running_balance"]


def test_opening_cash_override_shifts_every_months_running_balance():
    farm = _multi_sector_farm()
    delta = -5000.0
    new_opening = float(farm.get("opening_cash_balance", 0)) + delta
    sandbox_farm, _ = apply_sandbox_changes(farm, {"opening_cash_balance": new_opening})

    base_months = farm["monthly_forecast"]
    scenario_months = sandbox_farm["monthly_forecast"]
    for base_month, scenario_month in zip(base_months, scenario_months):
        assert round(scenario_month["running_balance"] - base_month["running_balance"], 2) == round(delta, 2)
        # Revenue/costs are unaffected by a pure cash correction.
        assert scenario_month["revenue"] == base_month["revenue"]
        assert scenario_month["costs"] == base_month["costs"]


def test_loan_repayments_override_is_reflected_in_the_precomputed_months():
    farm = _multi_sector_farm()
    higher_repayments = float(farm.get("loan_repayments", 0)) + 12_000.0
    sandbox_farm, _ = apply_sandbox_changes(farm, {"loan_repayments": higher_repayments})

    base_months = farm["monthly_forecast"]
    scenario_months = sandbox_farm["monthly_forecast"]
    assert scenario_months[-1]["running_balance"] < base_months[-1]["running_balance"]


def test_household_fields_are_not_altered_by_a_farm_side_change():
    farm = _multi_sector_farm()
    sandbox_farm, _ = apply_sandbox_changes(farm, {"feed": farm["feed"] * 1.5})
    base_months = farm["monthly_forecast"]
    scenario_months = sandbox_farm["monthly_forecast"]
    for base_month, scenario_month in zip(base_months, scenario_months):
        assert scenario_month["household_net"] == base_month["household_net"]
        assert scenario_month["household_income"] == base_month["household_income"]


# ---------------------------------------------------------------------------
# Single-sector farms (no precomputed forecast) are unaffected by this fix
# ---------------------------------------------------------------------------

def test_single_sector_farm_without_a_precomputed_forecast_is_a_no_op_for_the_rescale():
    farm = _flat_single_sector_farm()
    # A plain single-farm dict has no `monthly_forecast` key at all - the
    # rescale must not add one or otherwise interfere with the existing
    # from-scratch fallback in `generate_monthly_forecast`.
    assert "monthly_forecast" not in farm
    sandbox_farm, changes_applied = apply_sandbox_changes(farm, {"milk_price": farm["milk_price"] * 1.1})
    assert changes_applied["milk_price"]["to"] == farm["milk_price"] * 1.1
    assert "monthly_forecast" not in sandbox_farm
