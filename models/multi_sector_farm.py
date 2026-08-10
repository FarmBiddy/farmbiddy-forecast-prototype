"""Constants and helpers for multi-sector farm datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

MULTI_SECTOR_FILE = "multi_sector_farm.json"
SCHEMA_VERSION = "2.0"
VALID_SECTORS = ("dairy", "beef", "lamb")

SECTOR_LABELS = {
    "dairy": "Dairy",
    "beef": "Beef",
    "lamb": "Lamb",
}

DEFAULT_SECTORS = list(VALID_SECTORS)


@dataclass
class LoanRecord:
    """Normalised per-lender loan detail with an estimated amortisation position.

    The dataset only stores ``principal``, ``rate``, ``monthly_repayment``, and
    ``maturity`` for each loan (no start date or amortisation schedule), so
    ``outstanding_balance`` and ``years_remaining`` are estimates derived from
    those four fields rather than fabricated new data.
    """

    lender: str
    principal: float
    monthly_repayment: float
    rate: float
    maturity: str
    months_remaining: int
    years_remaining: float
    outstanding_balance: float


def _months_between(today: date, maturity: date) -> int:
    months = (maturity.year - today.year) * 12 + (maturity.month - today.month)
    return max(months, 0)


def _parse_maturity(maturity_raw: str, fallback: date) -> date:
    try:
        year_str, month_str = str(maturity_raw).split("-")[:2]
        return date(int(year_str), int(month_str), 1)
    except (ValueError, TypeError, AttributeError):
        return fallback


def estimate_loan_position(loan: dict, as_of: date | None = None) -> dict:
    """Estimate a lender loan's outstanding balance and years remaining.

    Outstanding balance is estimated as the present value of the remaining
    monthly repayments to maturity, discounted at the loan's own monthly
    interest rate — the standard formula for the balance of a fixed-payment
    amortising loan with ``n`` periods left:

        balance ~= monthly_repayment * (1 - (1 + r) ** -n) / r

    where ``r`` is the monthly rate and ``n`` is the number of months
    remaining until ``maturity``. The result is capped at the original
    principal as a sanity floor. This only uses fields already present in
    the dataset (no fabricated data).
    """
    reference = as_of or date.today()
    principal = float(loan.get("principal") or 0)
    monthly_repayment = float(loan.get("monthly_repayment") or 0)
    annual_rate = float(loan.get("rate") or 0)
    maturity_raw = str(loan.get("maturity") or "")
    maturity_date = _parse_maturity(maturity_raw, reference)

    months_remaining = _months_between(reference, maturity_date)
    monthly_rate = annual_rate / 100 / 12

    if months_remaining <= 0 or monthly_repayment <= 0:
        outstanding = 0.0
    elif monthly_rate <= 0:
        outstanding = monthly_repayment * months_remaining
    else:
        outstanding = monthly_repayment * (1 - (1 + monthly_rate) ** -months_remaining) / monthly_rate

    outstanding = max(0.0, outstanding)
    if principal > 0:
        outstanding = min(outstanding, principal)

    return {
        "lender": loan.get("lender") or "Lender",
        "principal": round(principal, 2),
        "monthly_repayment": round(monthly_repayment, 2),
        "rate": round(annual_rate, 3),
        "maturity": maturity_raw,
        "months_remaining": months_remaining,
        "years_remaining": round(months_remaining / 12, 1),
        "outstanding_balance": round(outstanding, 2),
    }


def build_debt_register(loans: list[dict] | None, as_of: date | None = None) -> list[dict]:
    """Per-lender debt register: outstanding balance, rate, and years remaining."""
    return [estimate_loan_position(loan, as_of) for loan in (loans or [])]


def compute_household_month(household: dict | None, month: int) -> dict:
    """Household-only cash movement for a given calendar month (1-12).

    Additive on top of the farm dataset: drawings/living costs, off-farm
    income, and pension/insurance are modelled as constant monthly figures;
    tax lands as a lump sum in its configured payment month(s) - the same
    pattern `scheme_payments`/`scheme_payment_months` uses for farm income.
    """
    household = household or {}
    income = float(household.get("off_farm_income_monthly") or 0)
    transfer_in = float(household.get("farm_to_household_transfer_monthly") or 0)
    outgoings = (
        float(household.get("drawings_monthly") or 0)
        + float(household.get("pension_insurance_monthly") or 0)
    )
    tax_annual = float(household.get("tax_annual") or 0)
    tax_months = household.get("tax_payment_months") or []
    if tax_months and month in tax_months:
        outgoings += tax_annual / len(tax_months)

    return {
        "income": round(income, 2),
        "transfer_in": round(transfer_in, 2),
        "outgoings": round(outgoings, 2),
        "net": round(income + transfer_in - outgoings, 2),
    }
