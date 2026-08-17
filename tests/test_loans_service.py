"""Unit tests for Loans & Finance summary-first view (P1.4)."""

from __future__ import annotations

from services.loans_service import (
    LOW_CASH_ALERT_WHAT,
    build_loans_summary,
    low_cash_interaction,
    next_loan_to_clear,
    total_annual_repayments,
    total_outstanding_debt,
)


def _register():
    return [
        {
            "lender": "AIB Agri Finance",
            "monthly_repayment": 2100,
            "outstanding_balance": 120000,
            "months_remaining": 60,
        },
        {
            "lender": "Credit Union Cahir",
            "monthly_repayment": 680,
            "outstanding_balance": 8000,
            "months_remaining": 12,
        },
    ]


def test_total_outstanding_debt_sums_register():
    assert total_outstanding_debt(_register()) == 128000


def test_total_annual_repayments_sums_monthly_times_12():
    assert total_annual_repayments(_register()) == (2100 + 680) * 12


def test_totals_are_zero_for_empty_register():
    assert total_outstanding_debt([]) == 0
    assert total_annual_repayments(None) == 0


def test_next_loan_to_clear_picks_fewest_months_remaining():
    next_loan = next_loan_to_clear(_register())
    assert next_loan["lender"] == "Credit Union Cahir"


def test_next_loan_to_clear_ignores_already_cleared_loans():
    register = _register()
    register.append({
        "lender": "Paid Off Co-op",
        "monthly_repayment": 0,
        "outstanding_balance": 0,
        "months_remaining": 0,
    })
    next_loan = next_loan_to_clear(register)
    assert next_loan["lender"] == "Credit Union Cahir"


def test_next_loan_to_clear_is_none_for_no_outstanding_loans():
    assert next_loan_to_clear([]) is None
    assert next_loan_to_clear([{"outstanding_balance": 0, "months_remaining": 0}]) is None


def test_low_cash_interaction_finds_matching_alert():
    alerts = [
        {"what": "Forecast annual loss", "severity": "high"},
        {"what": LOW_CASH_ALERT_WHAT, "severity": "high", "when": "Month 4"},
    ]
    found = low_cash_interaction(alerts)
    assert found is not None
    assert found["when"] == "Month 4"


def test_low_cash_interaction_is_none_when_absent():
    alerts = [{"what": "Forecast annual loss", "severity": "high"}]
    assert low_cash_interaction(alerts) is None
    assert low_cash_interaction(None) is None
    assert low_cash_interaction([]) is None


def test_build_loans_summary_full_payload():
    register = _register()
    alerts = [{"what": LOW_CASH_ALERT_WHAT, "severity": "high"}]
    summary = build_loans_summary(register, alerts)

    assert summary["loan_count"] == 2
    assert summary["total_outstanding_debt"] == 128000
    assert summary["total_annual_repayments"] == (2100 + 680) * 12
    assert summary["next_loan_to_clear"]["lender"] == "Credit Union Cahir"
    assert summary["low_cash_interaction"]["what"] == LOW_CASH_ALERT_WHAT
    assert summary["loans"] == register


def test_build_loans_summary_with_no_loans():
    summary = build_loans_summary([], [])
    assert summary["loan_count"] == 0
    assert summary["total_outstanding_debt"] == 0
    assert summary["total_annual_repayments"] == 0
    assert summary["next_loan_to_clear"] is None
    assert summary["low_cash_interaction"] is None
    assert summary["loans"] == []
