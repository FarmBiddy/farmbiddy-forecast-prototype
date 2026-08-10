"""Tests for practical cash-flow action testing (Teagasc item 6)."""

from __future__ import annotations

from forecast_engine.cashflow_actions import (
    ALL_ACTIONS,
    NO_LATER_MONTH_MESSAGE,
    apply_adjust_loan_timing,
    apply_bring_forward_sales,
    apply_cashflow_action,
    apply_defer_purchases,
    apply_match_payments_to_surplus,
    apply_use_short_term_credit,
    lowest_balance_and_deficits,
)


def _build_months(cashflows: list[float]) -> list[dict]:
    """Build a synthetic combined monthly forecast from a list of monthly net cash flows."""
    running = 0.0
    months = []
    for i, cf in enumerate(cashflows, start=1):
        running += cf
        months.append({"month": i, "combined_cashflow": cf, "combined_running_balance": round(running, 2)})
    return months


def test_lowest_balance_and_deficits_basic():
    # Running balances: 1000, -4000, -2000, -3000 -> 3 months with a negative balance.
    months = _build_months([1000, -5000, 2000, -1000])
    metrics = lowest_balance_and_deficits(months)
    assert metrics["lowest_balance"] == -4000
    assert metrics["lowest_balance_month"] == 2
    assert metrics["deficit_months"] == 3


def test_lowest_balance_and_deficits_empty():
    assert lowest_balance_and_deficits([]) == {"lowest_balance": 0.0, "lowest_balance_month": None, "deficit_months": 0}


def test_bring_forward_sales_pulls_from_later_surplus_month():
    # Deficit in month 2, healthy surplus in month 4 (later).
    months = _build_months([1000, -3000, 500, 4000, 1000])
    scenario, description = apply_bring_forward_sales(months, to_month=2)
    assert "month 4" in description
    assert "month 2" in description
    lowest_before = lowest_balance_and_deficits(months)["lowest_balance"]
    lowest_after = lowest_balance_and_deficits(scenario)["lowest_balance"]
    assert lowest_after >= lowest_before


def test_bring_forward_sales_no_later_month_returns_unchanged():
    months = _build_months([1000, -3000, 500])
    scenario, description = apply_bring_forward_sales(months, to_month=3)
    assert description == NO_LATER_MONTH_MESSAGE
    assert scenario == months


def test_defer_purchases_moves_expense_later():
    months = _build_months([1000, -3000, 500, 4000])
    scenario, description = apply_defer_purchases(months, from_month=2)
    assert "month 2" in description
    scenario_month2 = next(m for m in scenario if m["month"] == 2)
    original_month2 = next(m for m in months if m["month"] == 2)
    assert scenario_month2["combined_cashflow"] > original_month2["combined_cashflow"]


def test_defer_purchases_no_later_month_returns_unchanged():
    months = _build_months([1000, -3000])
    scenario, description = apply_defer_purchases(months, from_month=2)
    assert description == NO_LATER_MONTH_MESSAGE
    assert scenario == months


def test_adjust_loan_timing_same_mechanic_as_defer():
    months = _build_months([1000, -3000, 500, 4000])
    scenario, description = apply_adjust_loan_timing(months, from_month=2, amount=1500)
    assert "loan repayment" in description
    scenario_month2 = next(m for m in scenario if m["month"] == 2)
    assert scenario_month2["combined_cashflow"] == -1500


def test_match_payments_to_surplus_targets_best_month():
    months = _build_months([1000, -3000, 500, 4000, 200])
    scenario, description = apply_match_payments_to_surplus(months, payment_month=2)
    assert "month 4" in description  # month 4 has the highest cashflow


def test_use_short_term_credit_draws_and_repays_with_interest():
    months = _build_months([1000, -3000, 500, 4000])
    scenario, description = apply_use_short_term_credit(months, draw_month=2, amount=3000, annual_rate=12)
    draw = next(m for m in scenario if m["month"] == 2)
    assert draw["combined_cashflow"] == -3000 + 3000  # gap fully covered
    repay = next(m for m in scenario if m["month"] == 4)
    assert repay["combined_cashflow"] < 4000  # interest + principal deducted
    assert "interest" in description


def test_use_short_term_credit_no_later_month_leaves_outstanding():
    months = _build_months([1000, -3000])
    scenario, description = apply_use_short_term_credit(months, draw_month=2, amount=3000)
    draw = next(m for m in scenario if m["month"] == 2)
    assert draw["combined_cashflow"] == -3000 + 3000
    assert "carry forward" in description


def test_apply_cashflow_action_dispatches_all_five():
    months = _build_months([1000, -3000, 500, 4000, -1000, 2000])
    for action in ALL_ACTIONS:
        scenario, description = apply_cashflow_action(action, months)
        assert isinstance(description, str) and description
        assert len(scenario) == len(months)


def test_apply_cashflow_action_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        apply_cashflow_action("not_a_real_action", _build_months([1000]))
