"""Lightweight data-quality checks (Phase 9 / UX item 12).

Not a validation service — a handful of sanity checks over data already
loaded for the dashboard, each naming the affected area so the frontend can
show a banner near that figure rather than one generic global notice. This
module has no project dependencies so it can be imported anywhere without
risking circular imports.
"""

from __future__ import annotations

from datetime import date

STALE_MONTHS_THRESHOLD = 2
RECONCILE_TOLERANCE_PCT = 5.0


def _parse_period(period: str) -> tuple[int, int] | None:
    try:
        year_str, month_str = str(period).split("-")[:2]
        return int(year_str), int(month_str)
    except (ValueError, AttributeError, TypeError):
        return None


def _months_since(period: str, today: date) -> int | None:
    parsed = _parse_period(period)
    if not parsed:
        return None
    year, month = parsed
    return (today.year - year) * 12 + (today.month - month)


def check_data_freshness(latest_period: str | None, today: date | None = None) -> list[dict]:
    """Flag when the most recent month of farm data is stale."""
    today = today or date.today()
    if not latest_period:
        return [{
            "type": "missing_data",
            "area": "Farm Data",
            "severity": "medium",
            "message": "No dated farm data was found — figures may be using defaults rather than real records.",
        }]
    age = _months_since(latest_period, today)
    if age is None or age <= STALE_MONTHS_THRESHOLD:
        return []
    return [{
        "type": "outdated_data",
        "area": "Farm Data",
        "severity": "high" if age >= 6 else "medium",
        "message": (
            f"Farm records were last updated {age} months ago (most recent month: {latest_period}). "
            "Figures may not reflect current prices, costs, or herd numbers."
        ),
    }]


def check_missing_required_fields(farm: dict) -> list[dict]:
    """Flag core inputs the forecast depends on that are missing entirely."""
    warnings: list[dict] = []
    required = [
        ("opening_cash_balance", "Cash Available"),
        ("milk_price", "Milk Price"),
    ]
    for field, area in required:
        if farm.get(field) is None:
            warnings.append({
                "type": "missing_data",
                "area": area,
                "severity": "medium",
                "message": f"'{field.replace('_', ' ')}' is missing from the farm record — the forecast is using a default assumption instead.",
            })
    return warnings


def check_loan_assumptions(debt_register: list[dict] | None, raw_loans: list[dict] | None) -> list[dict]:
    """Flag lenders whose outstanding-balance estimate relies on assumed/missing detail."""
    warnings: list[dict] = []
    raw_by_lender = {loan.get("lender"): loan for loan in (raw_loans or [])}
    for entry in debt_register or []:
        lender = entry.get("lender")
        raw = raw_by_lender.get(lender) or {}
        missing = [f for f in ("rate", "maturity", "monthly_repayment") if not raw.get(f)]
        if missing:
            warnings.append({
                "type": "incomplete_assumptions",
                "area": "Debt Register",
                "severity": "low",
                "message": (
                    f"{lender or 'A lender'}: outstanding balance is estimated because "
                    f"{', '.join(missing)} is missing from the loan record."
                ),
            })
    return warnings


def check_revenue_reconciliation(forecast_summary: dict, monthly_forecast: list[dict] | None) -> list[dict]:
    """Flag when the annual summary figure disagrees with the sum of the 12 monthly figures."""
    monthly_forecast = monthly_forecast or []
    if not monthly_forecast:
        return []
    annual_revenue = float(forecast_summary.get("annual_revenue") or 0)
    monthly_sum = sum(float(m.get("revenue") or 0) for m in monthly_forecast)
    if annual_revenue <= 0 or monthly_sum <= 0:
        return []
    diff_pct = abs(annual_revenue - monthly_sum) / annual_revenue * 100
    if diff_pct <= RECONCILE_TOLERANCE_PCT:
        return []
    return [{
        "type": "reconciliation",
        "area": "Revenue",
        "severity": "medium",
        "message": (
            f"Annual revenue (€{annual_revenue:,.0f}) doesn't match the sum of the 12 forecast months "
            f"(€{monthly_sum:,.0f}) — a {diff_pct:.0f}% difference. Treat one of these two figures with "
            "caution until reconciled."
        ),
    }]


def check_sample_data(profile: dict | None) -> list[dict]:
    """Flag when the active farm profile is known sample/demo data, not real financial records."""
    if not (profile or {}).get("is_sample_data"):
        return []
    return [{
        "type": "sample_data",
        "area": "Farm Profile",
        "severity": "low",
        "message": "This farm is currently using sample/demo data, not your own financial records.",
    }]


def build_data_quality_warnings(
    farm: dict,
    profile: dict | None,
    forecast_summary: dict,
    monthly_forecast: list[dict] | None = None,
    debt_register: list[dict] | None = None,
    latest_period: str | None = None,
    today: date | None = None,
) -> list[dict]:
    """Run all data-quality checks and return the combined warning list."""
    warnings: list[dict] = []
    warnings += check_sample_data(profile)
    warnings += check_data_freshness(latest_period, today)
    warnings += check_missing_required_fields(farm)
    warnings += check_loan_assumptions(debt_register, farm.get("_loans"))
    warnings += check_revenue_reconciliation(forecast_summary, monthly_forecast)
    return warnings
