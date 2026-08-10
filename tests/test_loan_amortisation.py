"""Tests for the per-lender loan amortisation estimate."""

from __future__ import annotations

from datetime import date

from models.multi_sector_farm import build_debt_register, estimate_loan_position


def test_estimate_loan_position_basic_fields():
    loan = {
        "lender": "AIB Agri Finance",
        "principal": 185000,
        "monthly_repayment": 2100,
        "rate": 4.85,
        "maturity": "2031-06",
    }
    result = estimate_loan_position(loan, as_of=date(2026, 7, 1))
    assert result["lender"] == "AIB Agri Finance"
    assert result["months_remaining"] == 59
    assert result["years_remaining"] == round(59 / 12, 1)
    assert 0 < result["outstanding_balance"] <= loan["principal"]


def test_estimate_loan_position_matured_loan_has_zero_balance():
    loan = {
        "lender": "Credit Union Cahir",
        "principal": 35000,
        "monthly_repayment": 680,
        "rate": 5.2,
        "maturity": "2020-01",
    }
    result = estimate_loan_position(loan, as_of=date(2026, 7, 1))
    assert result["months_remaining"] == 0
    assert result["outstanding_balance"] == 0.0
    assert result["years_remaining"] == 0.0


def test_estimate_loan_position_handles_zero_rate():
    loan = {
        "lender": "Interest-free loan",
        "principal": 12000,
        "monthly_repayment": 500,
        "rate": 0,
        "maturity": "2028-01",
    }
    result = estimate_loan_position(loan, as_of=date(2026, 1, 1))
    assert result["months_remaining"] == 24
    assert result["outstanding_balance"] == 12000.0


def test_estimate_loan_position_missing_maturity_defaults_safely():
    loan = {"lender": "Unknown", "principal": 5000, "monthly_repayment": 100, "rate": 5}
    result = estimate_loan_position(loan, as_of=date(2026, 1, 1))
    assert result["months_remaining"] == 0
    assert result["outstanding_balance"] == 0.0


def test_build_debt_register_multiple_loans():
    loans = [
        {"lender": "A", "principal": 100000, "monthly_repayment": 1000, "rate": 4, "maturity": "2030-01"},
        {"lender": "B", "principal": 20000, "monthly_repayment": 400, "rate": 6, "maturity": "2029-06"},
    ]
    register = build_debt_register(loans, as_of=date(2026, 1, 1))
    assert len(register) == 2
    assert {loan["lender"] for loan in register} == {"A", "B"}


def test_build_debt_register_empty():
    assert build_debt_register(None) == []
    assert build_debt_register([]) == []
