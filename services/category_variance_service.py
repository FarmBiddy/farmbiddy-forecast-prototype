"""
Category-level Budget vs Actual comparison (P0.3).

Answers: "You are EUR X ahead/behind budget" and then "which categories are
driving that" (e.g. "Feed EUR120 above budget", "Milk income EUR340 below
budget") - without ever fabricating a budget figure that the farmer never
set.

Actuals reuse the exact same monthly category totals already computed for
the Income & Expenses view (`services/income_expense_service.py`'s dataset
mapping, plus the farmer's manual `FinancialRecord` ledger) - one Actuals
definition, not a second copy of the aggregation logic. This is structured
so that once invoices/receipts (P1.2) and other origins feed the same
`FinancialRecord` store, this service picks them up automatically with no
change here.

Budgets come only from `services/category_budget_service.py` - a category
with no budget entry for a given month is simply excluded from that
month's comparison; a category with *no* budget anywhere in the window is
reported with `status="no_budget_set"`, never a fabricated zero variance.

Double-counting guard (P0.4): the dataset's monthly figures are already
complete, aggregated totals for the months they cover. A manual record
dated inside that coverage window is therefore NOT added into Actuals
here (it would double-count against a figure the dataset already
includes) - only records dated after `dataset_coverage_cutoff` are folded
in, and the comparison window is extended to include those newer,
manual-only months. See `services.dashboard_summary.compute_actual_cash_flow`
for the identical rule applied to the Overview/whole-farm Budget vs Actual.
"""

from __future__ import annotations

from forecast_engine.period_labels import trailing_12_months
from models.financial_record import category_label
from services.category_budget_service import budget_lookup
from services.financial_record_service import list_financial_records, monthly_category_totals as manual_monthly_category_totals
from services.income_expense_service import dataset_monthly_category_totals, window_months
from services.dashboard_summary import dataset_coverage_cutoff, get_selected_sector_data

TOLERANCE_FLOOR = 10.0
TOLERANCE_RATE = 0.03


def _status_and_summary(record_type: str, category_id: str, label: str, difference: float, budget_total: float) -> tuple[str, str]:
    tolerance = max(TOLERANCE_FLOOR, TOLERANCE_RATE * abs(budget_total))
    if abs(difference) <= tolerance:
        return "on_budget", f"{label} is on budget."

    amount = abs(round(difference, 0))
    if record_type == "expense":
        if difference > 0:
            return "above_budget", f"{label} is €{amount:,.0f} above budget."
        return "below_budget", f"{label} is €{amount:,.0f} below budget."
    if difference > 0:
        return "ahead", f"{label} is €{amount:,.0f} ahead of budget."
    return "behind", f"{label} is €{amount:,.0f} behind budget."


def build_category_budget_vs_actual(
    farm_file: str,
    sectors: list[str],
    filtered_raw: dict | None = None,
    months: int = 12,
) -> dict:
    """Full category-level Budget vs Actual payload for the given farm/sectors."""
    filtered = filtered_raw or get_selected_sector_data(farm_file, sectors)
    selected = filtered.get("selected_sectors") or sectors or []

    dataset_window = window_months(filtered, months=months)
    cutoff = dataset_coverage_cutoff(filtered)
    dataset_actuals = dataset_monthly_category_totals(filtered, months=months)

    def _record_year_month(record: dict) -> tuple | None:
        date = record.get("date") or ""
        if len(date) < 7:
            return None
        try:
            return (int(date[0:4]), int(date[5:7]))
        except ValueError:
            return None

    # Only records dated after the dataset's own coverage are added to
    # Actuals - a record inside that coverage would double-count against a
    # month the dataset already totals up (see module docstring).
    manual_records_new = [
        r for r in list_financial_records(farm_file, sectors=selected)
        if (ym := _record_year_month(r)) is not None and (cutoff is None or ym > cutoff)
    ]
    manual_actuals = manual_monthly_category_totals(manual_records_new)

    manual_only_months = sorted({(y, m) for (y, m, _rt, _cat) in manual_actuals.keys()})
    window = sorted(set(dataset_window) | set(manual_only_months))
    window_set = set(window)

    actual_totals: dict[tuple, float] = dict(dataset_actuals)
    for key, value in manual_actuals.items():
        actual_totals[key] = round(actual_totals.get(key, 0.0) + value, 2)

    resolved_budgets = budget_lookup(farm_file, sectors=selected)

    # Every category that has EITHER a budget in-window OR an actual in-window,
    # so a category with spend but no budget still surfaces as "no_budget_set"
    # rather than silently disappearing from the report.
    category_keys: set[tuple[str, str]] = set()
    for (rt, cat, year, month), _ in resolved_budgets.items():
        if (year, month) in window_set:
            category_keys.add((rt, cat))
    for (year, month, rt, cat) in actual_totals.keys():
        if (year, month) in window_set and rt and cat:
            category_keys.add((rt, cat))

    rows = []
    for record_type, category_id in sorted(category_keys):
        label = category_label(record_type, category_id)
        months_with_budget = 0
        budget_sum = 0.0
        actual_sum_for_budgeted_months = 0.0
        for (year, month) in window:
            budget_entry = resolved_budgets.get((record_type, category_id, year, month))
            if budget_entry is None:
                continue
            months_with_budget += 1
            budget_sum += float(budget_entry["amount"])
            actual_sum_for_budgeted_months += float(actual_totals.get((year, month, record_type, category_id), 0.0))

        if months_with_budget == 0:
            rows.append({
                "record_type": record_type,
                "category_id": category_id,
                "label": label,
                "status": "no_budget_set",
                "budget_total": None,
                "actual_total": None,
                "difference": None,
                "months_with_budget": 0,
                "months_in_window": len(window),
                "summary": f"No budget set for {label} yet.",
            })
            continue

        budget_total = round(budget_sum, 2)
        actual_total = round(actual_sum_for_budgeted_months, 2)
        difference = round(actual_total - budget_total, 2)
        status, summary = _status_and_summary(record_type, category_id, label, difference, budget_total)
        rows.append({
            "record_type": record_type,
            "category_id": category_id,
            "label": label,
            "status": status,
            "budget_total": budget_total,
            "actual_total": actual_total,
            "difference": difference,
            "months_with_budget": months_with_budget,
            "months_in_window": len(window),
            "summary": summary,
        })

    budgeted_rows = [r for r in rows if r["status"] != "no_budget_set"]
    unbudgeted_rows = [r for r in rows if r["status"] == "no_budget_set"]
    budgeted_rows.sort(key=lambda r: r["category_id"])
    unbudgeted_rows.sort(key=lambda r: r["category_id"])

    top_contributors = sorted(
        [r for r in budgeted_rows if r["status"] != "on_budget"],
        key=lambda r: abs(r["difference"]),
        reverse=True,
    )[:5]

    if not budgeted_rows:
        overall_status = "no_budget_set"
        overall_budget_total = None
        overall_actual_total = None
        overall_difference = None
        overall_summary = "No category budgets have been set yet."
    else:
        # Net position across every category with a budget: income budgeted-
        # over-achieved minus expense budgeted-over-spent, i.e. actual net
        # relative to budgeted net for exactly the categories/months compared.
        overall_budget_net = sum(
            (r["budget_total"] if r["record_type"] == "income" else -r["budget_total"]) for r in budgeted_rows
        )
        overall_actual_net = sum(
            (r["actual_total"] if r["record_type"] == "income" else -r["actual_total"]) for r in budgeted_rows
        )
        overall_budget_total = round(overall_budget_net, 2)
        overall_actual_total = round(overall_actual_net, 2)
        overall_difference = round(overall_actual_net - overall_budget_net, 2)
        tolerance = max(TOLERANCE_FLOOR, TOLERANCE_RATE * abs(overall_budget_total))
        if abs(overall_difference) <= tolerance:
            overall_status = "on_budget"
            overall_summary = "You are on budget across the categories you've set a budget for."
        elif overall_difference > 0:
            overall_status = "ahead"
            overall_summary = f"You are €{abs(round(overall_difference, 0)):,.0f} ahead of budget across the categories you've set."
        else:
            overall_status = "behind"
            overall_summary = f"You are €{abs(round(overall_difference, 0)):,.0f} behind budget across the categories you've set."

    return {
        "success": True,
        "farm_name": filtered.get("farm_name", "Farm"),
        "selected_sectors": selected,
        "period": trailing_12_months(),
        "months_in_window": len(window),
        "overall_status": overall_status,
        "overall_budget_total": overall_budget_total,
        "overall_actual_total": overall_actual_total,
        "overall_difference": overall_difference,
        "overall_summary": overall_summary,
        "top_contributors": top_contributors,
        "categories": budgeted_rows,
        "unbudgeted_categories": unbudgeted_rows,
    }
