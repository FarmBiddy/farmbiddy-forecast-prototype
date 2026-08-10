"""
Monthly cash-flow budget vs. actual comparison (Teagasc items 1-2).

Compares the committed `cash_flow_budget` entries in the farm dataset
against the same farm+household-aware actual cash-flow figure Phase 2
introduced (`combined_cashflow` in services/multi_sector_farm.py), so
"actual" always means the same thing on both sides of the comparison.
"""

from __future__ import annotations

from forecast_engine.cashflow_classifier import classify_cashflow_entries
from forecast_engine.period_labels import historical_month
from models.multi_sector_farm import build_debt_register, compute_household_month
from services.dashboard_summary import get_selected_sector_data, get_sector_monthly_history
from services.multi_sector_farm import aggregate_sector_financials

DEFICIT = "deficit"
SURPLUS = "surplus"
BREAKEVEN = "breakeven"

AHEAD = "ahead"
BEHIND = "behind"
ON_BUDGET = "on_budget"


def _loan_monthly_total(farm_summary: dict) -> float:
    loans = (farm_summary or {}).get("loans") or []
    return sum(float(loan.get("monthly_repayment") or 0) for loan in loans)


def get_budget_entries(farm: dict) -> list[dict]:
    """Raw `cash_flow_budget` entries from the dataset, oldest first."""
    entries = farm.get("cash_flow_budget") or []
    return sorted(entries, key=lambda e: (e.get("year", 0), e.get("month", 0)))


def _scheme_payment_for_month(farm: dict, month: int) -> float:
    """Scheme income landing in this calendar month, applied every year.

    Scheme payments (BISS/ACRES/other grants) are stored as annual totals
    with a single payment month, the same way `_build_monthly_forecast`
    (services/multi_sector_farm.py) treats them for the forward projection -
    reused here so historical actuals aren't understated.
    """
    scheme = (farm or {}).get("scheme_payments") or {}
    scheme_months = scheme.get("scheme_payment_months") or {}
    total = 0.0
    for key in ("biss", "acres", "other_grants"):
        if scheme_months.get(key) == month:
            total += float(scheme.get(key) or 0)
    return total


def compute_actual_cash_flow(filtered_raw: dict, farm_summary: dict, months: int = 24) -> dict[tuple, dict]:
    """Actual farm+household cash in/out per (year, month), keyed by period tuple.

    Mirrors the `combined_cashflow` definition from
    `services/multi_sector_farm.py`: sector revenue/costs plus scheme income
    and household income/outgoings for that calendar month, minus loan
    repayments.
    """
    household = (farm_summary or {}).get("household") or {}
    loan_monthly = _loan_monthly_total(farm_summary)
    combined, _ = get_sector_monthly_history(filtered_raw, months=months)

    actual: dict[tuple, dict] = {}
    for row in combined:
        year, month = row["year"], row["month"]
        hh = compute_household_month(household, month)
        scheme_income = _scheme_payment_for_month(filtered_raw, month)
        cash_in = round(row["revenue"] + scheme_income + hh["income"], 2)
        cash_out = round(row["costs"] + loan_monthly + hh["outgoings"], 2)
        actual[(year, month)] = {
            "year": year,
            "month": month,
            "period": row.get("period") or f"{year}-{month:02d}",
            "actual_cash_in": cash_in,
            "actual_cash_out": cash_out,
            "actual_net": round(cash_in - cash_out, 2),
        }
    return actual


def _cause_summary(cash_in_variance: float, cash_out_variance: float, net_variance: float, tolerance: float) -> str:
    if abs(net_variance) <= tolerance:
        return "On budget — cash in and cash out both close to plan."

    driver_is_cash_out = abs(cash_out_variance) >= abs(cash_in_variance)
    direction = "Ahead of" if net_variance > 0 else "Behind"
    amount = abs(round(net_variance, 0))

    if driver_is_cash_out:
        detail = "costs came in lower than budgeted" if cash_out_variance > 0 else "costs came in higher than budgeted"
    else:
        detail = "cash in was stronger than budgeted" if cash_in_variance > 0 else "cash in fell short of budget"

    return f"{direction} budget by €{amount:,.0f} — mainly because {detail}."


def _compare_entry(actual: dict, budget: dict) -> dict:
    budgeted_in = float(budget.get("expected_cash_in") or 0)
    budgeted_out = float(budget.get("expected_cash_out") or 0)
    budgeted_net = round(budgeted_in - budgeted_out, 2)

    actual_net = actual["actual_net"]
    net_variance = round(actual_net - budgeted_net, 2)
    cash_in_variance = round(actual["actual_cash_in"] - budgeted_in, 2)
    cash_out_variance = round(budgeted_out - actual["actual_cash_out"], 2)

    tolerance = max(50.0, 0.02 * abs(budgeted_net))

    if actual_net < 0:
        cashflow_status = DEFICIT
    elif actual_net > 0:
        cashflow_status = SURPLUS
    else:
        cashflow_status = BREAKEVEN

    if net_variance > tolerance:
        budget_status = AHEAD
    elif net_variance < -tolerance:
        budget_status = BEHIND
    else:
        budget_status = ON_BUDGET

    return {
        "period": actual["period"],
        "year": actual["year"],
        "month": actual["month"],
        "actual_cash_in": actual["actual_cash_in"],
        "actual_cash_out": actual["actual_cash_out"],
        "actual_net": actual_net,
        "budgeted_cash_in": round(budgeted_in, 2),
        "budgeted_cash_out": round(budgeted_out, 2),
        "budgeted_net": budgeted_net,
        "variance": net_variance,
        "cashflow_status": cashflow_status,
        "budget_status": budget_status,
        "cause_summary": _cause_summary(cash_in_variance, cash_out_variance, net_variance, tolerance),
        # Named distinctly from the existing "period" ("YYYY-MM") field above
        # to avoid overwriting it; this carries the Phase 10 period-type badge.
        "period_info": historical_month(actual["period"]),
    }


def compare_budget_vs_actual(
    farm_file: str,
    sectors: list[str],
    filtered_raw: dict | None = None,
    months: int = 24,
) -> dict:
    """Budget-vs-actual comparison for every month with both a budget and an actual figure."""
    filtered = filtered_raw or get_selected_sector_data(farm_file, sectors)
    farm_summary = filtered.get("farm_summary") or {}

    actual_by_period = compute_actual_cash_flow(filtered, farm_summary, months=months)
    budget_entries = get_budget_entries(filtered)

    entries = []
    for budget in budget_entries:
        key = (budget.get("year"), budget.get("month"))
        actual = actual_by_period.get(key)
        if not actual:
            continue
        entries.append(_compare_entry(actual, budget))

    entries.sort(key=lambda e: (e["year"], e["month"]))

    aggregated = aggregate_sector_financials(filtered)
    revenue_totals = aggregated.get("revenue_totals") or {}
    cost_totals = aggregated.get("cost_totals") or {}
    annual_revenue = float(revenue_totals.get("total") or 0)
    annual_costs = sum(float(v) for v in cost_totals.values())
    profit_margin = ((annual_revenue - annual_costs) / annual_revenue * 100) if annual_revenue else None
    debt_register = build_debt_register(farm_summary.get("loans") or [])

    entries = classify_cashflow_entries(
        entries,
        debt_register=debt_register,
        annual_revenue=annual_revenue,
        profit_margin=profit_margin,
    )

    deficit_months = sum(1 for e in entries if e["cashflow_status"] == DEFICIT)
    behind_budget_months = sum(1 for e in entries if e["budget_status"] == BEHIND)
    long_term_deficit_months = sum(1 for e in entries if e.get("classification") == "long_term")
    short_term_deficit_months = sum(1 for e in entries if e.get("classification") == "short_term")

    return {
        "success": True,
        "farm_name": filtered.get("farm_name", "Farm"),
        "selected_sectors": filtered.get("selected_sectors") or sectors or [],
        "entries": entries,
        "deficit_months": deficit_months,
        "behind_budget_months": behind_budget_months,
        "long_term_deficit_months": long_term_deficit_months,
        "short_term_deficit_months": short_term_deficit_months,
    }
