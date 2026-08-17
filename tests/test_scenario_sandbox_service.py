"""Tests for the What If? scenario sandbox (P2.1).

Uses the real multi_sector_farm.json dataset, as the other farm-file-based
service tests do, so `run_scenario_sandbox` exercises the real forecast
engine end to end rather than a synthetic farm dict.
"""

from __future__ import annotations

from services.scenario_sandbox_service import build_absolute_changes, run_scenario_sandbox

FARM = "multi_sector_farm.json"
SECTORS = ["dairy", "beef", "lamb"]


def _base_farm():
    return {
        "milk_price": 0.40,
        "feed": 20000.0,
        "fertiliser": 5000.0,
        "labour": 8000.0,
        "vet": 3000.0,
        "fuel": 2000.0,
        "electricity": 1500.0,
        "opening_cash_balance": 15000.0,
        "loan_repayments": 6000.0,
    }


# ---------------------------------------------------------------------------
# build_absolute_changes: preset -> engine-field mapping
# ---------------------------------------------------------------------------

def test_milk_price_cents_change_maps_to_an_absolute_milk_price():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {"milk_price_cents_change": -5})
    assert changes["milk_price"] == round(0.40 - 0.05, 4)


def test_milk_price_pct_change_maps_to_an_absolute_milk_price():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {"milk_price_pct_change": 10})
    assert changes["milk_price"] == round(0.40 * 1.10, 4)


def test_feed_and_fertiliser_pct_changes_map_to_absolute_costs():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {"feed_pct_change": 10, "fertiliser_pct_change": 20})
    assert changes["feed"] == round(20000.0 * 1.10, 2)
    assert changes["fertiliser"] == round(5000.0 * 1.20, 2)


def test_loan_repayments_is_an_absolute_override():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {"loan_repayments": 9000})
    assert changes["loan_repayments"] == 9000.0


def test_capital_purchase_deducts_from_todays_opening_cash():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {"capital_purchase_amount": 5000})
    assert changes["opening_cash_balance"] == 15000.0 - 5000.0


def test_capital_purchase_combines_with_an_explicit_cash_override():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {
        "opening_cash_balance": 20000.0,
        "capital_purchase_amount": 5000,
    })
    # The explicit override is the "true" starting cash; the purchase comes
    # off THAT figure, not off the farm's original opening_cash_balance.
    assert changes["opening_cash_balance"] == 20000.0 - 5000.0


def test_zero_capital_purchase_leaves_opening_cash_untouched():
    farm = _base_farm()
    changes = build_absolute_changes(farm, {"capital_purchase_amount": 0})
    assert "opening_cash_balance" not in changes


def test_no_inputs_produce_no_changes():
    farm = _base_farm()
    assert build_absolute_changes(farm, {}) == {}


# ---------------------------------------------------------------------------
# run_scenario_sandbox: end-to-end against the real forecast engine
# ---------------------------------------------------------------------------

def test_no_changes_scenario_equals_base_case():
    result = run_scenario_sandbox(FARM, {}, sectors=SECTORS)
    c = result["comparison"]
    assert c["profit_difference"] == 0
    assert c["min_cash_base"] == c["min_cash_scenario"]
    assert c["year_end_cash_base"] == c["year_end_cash_scenario"]
    assert c["additional_funding_pressure"] is False


def test_milk_price_drop_reduces_income_and_profit():
    result = run_scenario_sandbox(FARM, {"milk_price_pct_change": -10}, sectors=SECTORS)
    c = result["comparison"]
    assert c["revenue_scenario"] < c["revenue_base"]
    assert c["profit_scenario"] < c["profit_base"]
    assert c["revenue_difference"] < 0
    assert c["profit_difference"] < 0


def test_result_includes_year_end_cash_and_cash_shortage_metrics():
    result = run_scenario_sandbox(FARM, {"milk_price_pct_change": -10}, sectors=SECTORS)
    c = result["comparison"]
    for key in (
        "year_end_cash_base", "year_end_cash_scenario",
        "deficit_months_base", "deficit_months_scenario",
        "min_cash_month_base", "min_cash_month_scenario",
        "additional_funding_pressure",
    ):
        assert key in c


def test_large_capital_purchase_can_trigger_additional_funding_pressure():
    result = run_scenario_sandbox(FARM, {"capital_purchase_amount": 500_000}, sectors=SECTORS)
    c = result["comparison"]
    assert c["min_cash_scenario"] < c["min_cash_base"]
    assert c["additional_funding_pressure"] is True


def test_recommendations_flag_added_funding_pressure():
    result = run_scenario_sandbox(FARM, {"capital_purchase_amount": 500_000}, sectors=SECTORS)
    titles = [r["title"] for r in result["recommendations"]]
    assert any("cash-shortage" in t.lower() for t in titles)
