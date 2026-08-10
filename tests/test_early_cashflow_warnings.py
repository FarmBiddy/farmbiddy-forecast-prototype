"""Tests for the month-by-month early cash-flow warning scan (Teagasc item 7)."""

from __future__ import annotations

from forecast_engine.alerts import generate_alerts, generate_early_cashflow_warnings


def _months(balances, household_outgoings=None):
    return [
        {
            "month": i + 1,
            "combined_running_balance": bal,
            "household_outgoings": (household_outgoings[i] if household_outgoings else None),
        }
        for i, bal in enumerate(balances)
    ]


def test_no_warnings_when_all_balances_healthy():
    months = _months([5000, 6000, 7000, 8000])
    warnings = generate_early_cashflow_warnings(months)
    assert warnings == []


def test_empty_forecast_returns_no_warnings():
    assert generate_early_cashflow_warnings([]) == []
    assert generate_early_cashflow_warnings(None) == []


def test_future_negative_balance_is_flagged_with_month_span():
    months = _months([5000, 3000, -1000, -2000, 500])
    warnings = generate_early_cashflow_warnings(months)
    assert any("negative cash balance" in w and "months 3-4" in w for w in warnings)


def test_single_negative_month_uses_singular_phrasing():
    months = _months([5000, -500, 3000])
    warnings = generate_early_cashflow_warnings(months)
    assert any("negative cash balance in month 2" in w for w in warnings)


def test_increasing_overdraft_use_needs_three_worsening_months():
    # Negative and getting worse for 3 consecutive months (2, 3, 4).
    months = _months([1000, -500, -1500, -3000, -2000])
    warnings = generate_early_cashflow_warnings(months)
    assert any("Increasing overdraft use" in w and "3 consecutive" in w and "month 2" in w for w in warnings)


def test_two_worsening_months_does_not_trigger_overdraft_warning():
    months = _months([1000, -500, -1500, 4000])
    warnings = generate_early_cashflow_warnings(months)
    assert not any("Increasing overdraft use" in w for w in warnings)


def test_recovering_negative_months_do_not_count_as_worsening():
    # Negative every month but improving each time -> no widening trend.
    months = _months([-3000, -2000, -1000, -500])
    warnings = generate_early_cashflow_warnings(months)
    assert not any("Increasing overdraft use" in w for w in warnings)


def test_insufficient_cash_for_direct_debits_uses_loans_and_household():
    months = _months([1000, 200, 3000], household_outgoings=[1500, 1500, 1500])
    debt_register = [{"lender": "Bank", "monthly_repayment": 400}]
    warnings = generate_early_cashflow_warnings(months, debt_register)
    # Month 1 fixed outgoings = 400 + 1500 = 1900 > balance 1000.
    assert any("Insufficient cash for direct debits: month 1" in w for w in warnings)


def test_no_direct_debit_warning_when_no_recurring_outgoings_known():
    months = _months([100, 50, 3000])
    warnings = generate_early_cashflow_warnings(months, debt_register=None)
    assert not any("Insufficient cash for direct debits" in w for w in warnings)


def test_loan_repayments_in_low_cash_month_flagged():
    months = _months([5000, 300, 6000])
    debt_register = [{"lender": "Bank", "monthly_repayment": 500}]
    warnings = generate_early_cashflow_warnings(months, debt_register)
    assert any("Loan repayments due in a low-cash month: month 2" in w for w in warnings)


def test_no_loan_warning_without_debt_register():
    months = _months([5000, 300, 6000])
    warnings = generate_early_cashflow_warnings(months, debt_register=[])
    assert not any("Loan repayments due" in w for w in warnings)


def test_generate_alerts_is_backward_compatible_without_monthly_forecast():
    farm = {"opening_cash_balance": 10000, "feed": 500}
    alerts = generate_alerts(farm, profit=20000, revenue=100000, costs=80000, monthly_cashflow=500)
    assert not any("Cash-flow warning" in a or "Increasing overdraft" in a for a in alerts)


def test_generate_alerts_includes_early_warnings_when_monthly_forecast_given():
    farm = {"opening_cash_balance": 10000, "feed": 500}
    months = _months([5000, -500, -1500, -3000])
    alerts = generate_alerts(
        farm, profit=20000, revenue=100000, costs=80000, monthly_cashflow=500,
        monthly_forecast=months,
    )
    assert any("Cash-flow warning" in a for a in alerts)
    assert any("Increasing overdraft use" in a for a in alerts)
