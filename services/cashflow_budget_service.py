"""
Monthly cash-flow budget vs. actual comparison (Teagasc items 1-2).

Compares the committed `cash_flow_budget` entries in the farm dataset
against the same farm+household-aware actual cash-flow figure Phase 2
introduced (`combined_cashflow` in services/multi_sector_farm.py), so
"actual" always means the same thing on both sides of the comparison.

`compute_actual_cash_flow` and `get_budget_entries` live in
`services.dashboard_summary` (not here) so the Overview's current-period
and cash-position figures can share the exact same "actual" definition
without a circular import between the two modules.
"""

from __future__ import annotations

from forecast_engine.cashflow_classifier import classify_cashflow_entries
from forecast_engine.period_labels import historical_month
from models.multi_sector_farm import build_debt_register
from services.dashboard_summary import (
    compute_actual_cash_flow,
    get_budget_entries,
    get_selected_sector_data,
)
from services.multi_sector_farm import aggregate_sector_financials

DEFICIT = "deficit"
SURPLUS = "surplus"
BREAKEVEN = "breakeven"

AHEAD = "ahead"
BEHIND = "behind"
ON_BUDGET = "on_budget"


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
