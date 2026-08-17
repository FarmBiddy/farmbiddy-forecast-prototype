"""
Loans & Finance summary-first view (P1.4).

Presents the same per-lender debt register
(`models.multi_sector_farm.build_debt_register`) already used for the Debt
Register table and the cash-flow alerts/health score, led with four
glance-able figures before a farmer drills down to individual loans:

  * Total debt          - sum of outstanding_balance across the register.
  * Annual repayments   - sum of monthly_repayment * 12.
  * Next loan to clear  - the register entry with the fewest months
    remaining, i.e. which repayment commitment drops off first (freeing up
    that much cash per month). This is deliberately NOT "the loan with the
    biggest/soonest monthly instalment" - every loan's instalment recurs
    every month, so there is no single "next" instalment date to single
    out. A loan reaching maturity, by contrast, is a genuine one-off future
    event worth flagging.
  * Low-cash interaction - re-presents, rather than re-derives, whichever
    already-computed dashboard alert flags loan repayments landing in an
    already low-cash month (see forecast_engine.alerts /
    services.dashboard_summary.ALERT_DETAILS), so this page and Action Plan
    never disagree about the same underlying figures.

This module fabricates no new financial facts - every figure here is a
sum, min, or lookup over `debt_register`/`alerts` inputs computed
elsewhere and already covered by existing tests.
"""

from __future__ import annotations

LOW_CASH_ALERT_WHAT = "Loan repayments land in an already low-cash month"


def total_outstanding_debt(debt_register: list[dict] | None) -> float:
    return round(sum(float(loan.get("outstanding_balance") or 0) for loan in (debt_register or [])), 2)


def total_annual_repayments(debt_register: list[dict] | None) -> float:
    return round(sum(float(loan.get("monthly_repayment") or 0) * 12 for loan in (debt_register or [])), 2)


def next_loan_to_clear(debt_register: list[dict] | None) -> dict | None:
    """The loan with the fewest months remaining, excluding any already
    matured/zero-balance entries. None if there is nothing outstanding."""
    candidates = [
        loan for loan in (debt_register or [])
        if float(loan.get("outstanding_balance") or 0) > 0 and float(loan.get("months_remaining") or 0) > 0
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda loan: loan["months_remaining"])


def low_cash_interaction(alerts: list[dict] | None) -> dict | None:
    """The already-computed alert (if any) warning that loan repayments land
    in an already low-cash month. None means the current forecast has no
    such overlap - never fabricated, only looked up."""
    for alert in alerts or []:
        if alert.get("what") == LOW_CASH_ALERT_WHAT:
            return alert
    return None


def build_loans_summary(debt_register: list[dict] | None, alerts: list[dict] | None) -> dict:
    """Assemble the Loans & Finance summary-first payload."""
    register = debt_register or []
    return {
        "loan_count": len(register),
        "total_outstanding_debt": total_outstanding_debt(register),
        "total_annual_repayments": total_annual_repayments(register),
        "next_loan_to_clear": next_loan_to_clear(register),
        "low_cash_interaction": low_cash_interaction(alerts),
        "loans": register,
    }
