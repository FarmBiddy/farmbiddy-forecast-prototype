"""
Income & Expenses view (P0.2): "Where did my money come from / go?"

Two distinct, clearly-separated data sources feed this view, and they are
deliberately NOT merged into one number:

  1. The canonical multi-sector dataset's structured per-month revenue/cost
     line items - already-recorded historical actuals, trusted, and already
     used everywhere else (Budget vs Actual, the Overview). This is the
     primary category breakdown.
  2. The farmer's own manual financial-record ledger (services.financial_
     record_service) - quick day-to-day entries the farmer types in, shown
     as its own recent-entries list and its own totals.

Merging these two would risk double-counting a transaction that is both
already reflected in the dataset AND separately typed in by the farmer.
Until there is a real reconciliation rule for that (a P0.4 decision), they
stay side by side so no figure on screen is ever inflated by a duplicate.

Categories here are the generic, sector-agnostic vocabulary from
models.financial_record (Milk, Feed, Vet, ...), not the Dairy-shaped legacy
fields forecast_engine uses internally - this view must work the same way
for a beef- or sheep-only farm.
"""

from __future__ import annotations

from collections import defaultdict

from forecast_engine.period_labels import trailing_12_months
from models.financial_record import category_label
from services.dashboard_summary import (
    _loan_monthly_total,
    get_selected_sector_data,
    get_sector_monthly_history,
)
from services.financial_record_service import (
    category_choices_payload,
    list_financial_records,
    manual_totals,
)

RAW_REVENUE_TO_CATEGORY = {
    "milk": "milk",
    "cattle_sales": "livestock",
    "lamb_sales": "livestock",
    "wool": "other_income",
    "other": "other_income",
}

RAW_COST_TO_CATEGORY = {
    "feed": "feed",
    "fertiliser": "fertiliser",
    "vet": "veterinary",
    "breeding": "veterinary",
    "labour": "labour",
    "machinery": "machinery",
    "equipment": "machinery",
    "fuel": "fuel",
    "electricity": "utilities",
    "insurance": "insurance",
    "contractor": "contractor",
    "rent_land_lease": "other_expense",
    "animal_purchases": "other_expense",
    "housing": "other_expense",
}


def _dataset_category_breakdown(filtered_raw: dict, months: int = 12) -> tuple[list[dict], list[dict]]:
    """Farmer-facing category totals from the dataset's own structured
    revenue/cost line items, for the trailing `months`. See module
    docstring for why this is kept separate from manual entries.
    """
    income_totals: dict[str, float] = defaultdict(float)
    income_counts: dict[str, int] = defaultdict(int)
    expense_totals: dict[str, float] = defaultdict(float)
    expense_counts: dict[str, int] = defaultdict(int)

    for sector_data in (filtered_raw.get("sectors") or {}).values():
        monthly = (sector_data.get("monthly") or [])[-months:]
        for entry in monthly:
            for key, value in (entry.get("revenue") or {}).items():
                if key == "total" or not value:
                    continue
                category = RAW_REVENUE_TO_CATEGORY.get(key, "other_income")
                income_totals[category] += float(value)
                income_counts[category] += 1
            for key, value in (entry.get("costs") or {}).items():
                if key == "total" or not value:
                    continue
                category = RAW_COST_TO_CATEGORY.get(key, "other_expense")
                expense_totals[category] += float(value)
                expense_counts[category] += 1

    # Scheme payments (BISS/ACRES/other grants) land as a single annual sum
    # in whichever calendar month is configured - include it only when that
    # month falls inside the trailing window we're actually summarising,
    # the same rule services.dashboard_summary.compute_actual_cash_flow uses.
    scheme = filtered_raw.get("scheme_payments") or {}
    scheme_months = scheme.get("scheme_payment_months") or {}
    combined, _ = get_sector_monthly_history(filtered_raw, months=months)
    covered_months = {row["month"] for row in combined}
    for key in ("biss", "acres", "other_grants"):
        if scheme_months.get(key) in covered_months:
            amount = float(scheme.get(key) or 0)
            if amount:
                income_totals["grants_schemes"] += amount
                income_counts["grants_schemes"] += 1

    # Loan repayments are a real recurring cost but live in
    # farm_summary.loans, not any sector's monthly cost line items.
    farm_summary = filtered_raw.get("farm_summary") or {}
    loan_monthly = _loan_monthly_total(farm_summary)
    if loan_monthly:
        expense_totals["loan_repayments"] += round(loan_monthly * min(months, 12), 2)
        expense_counts["loan_repayments"] += 1

    income_rows = [
        {
            "category_id": cat, "label": category_label("income", cat),
            "total": round(total, 2), "count": income_counts[cat],
        }
        for cat, total in income_totals.items()
    ]
    expense_rows = [
        {
            "category_id": cat, "label": category_label("expense", cat),
            "total": round(total, 2), "count": expense_counts[cat],
        }
        for cat, total in expense_totals.items()
    ]
    income_rows.sort(key=lambda r: r["total"], reverse=True)
    expense_rows.sort(key=lambda r: r["total"], reverse=True)
    return income_rows, expense_rows


def dataset_monthly_category_totals(filtered_raw: dict, months: int = 24) -> dict[tuple, float]:
    """Per (year, month, record_type, category) actual totals from the
    dataset's own structured line items only (no manual records) - the
    same category vocabulary and mappings as `_dataset_category_breakdown`,
    but kept at monthly granularity so P0.3's category Budget vs Actual can
    compare against the same monthly budget records it stores.
    """
    totals: dict[tuple, float] = defaultdict(float)

    for sector_data in (filtered_raw.get("sectors") or {}).values():
        monthly = (sector_data.get("monthly") or [])[-months:]
        for entry in monthly:
            year = int(entry.get("year") or 0)
            month = int(entry.get("month") or 0)
            for key, value in (entry.get("revenue") or {}).items():
                if key == "total" or not value:
                    continue
                category = RAW_REVENUE_TO_CATEGORY.get(key, "other_income")
                totals[(year, month, "income", category)] += float(value)
            for key, value in (entry.get("costs") or {}).items():
                if key == "total" or not value:
                    continue
                category = RAW_COST_TO_CATEGORY.get(key, "other_expense")
                totals[(year, month, "expense", category)] += float(value)

    combined, _ = get_sector_monthly_history(filtered_raw, months=months)
    scheme = filtered_raw.get("scheme_payments") or {}
    scheme_months = scheme.get("scheme_payment_months") or {}
    for row in combined:
        year, month = row["year"], row["month"]
        for key in ("biss", "acres", "other_grants"):
            if scheme_months.get(key) == month:
                amount = float(scheme.get(key) or 0)
                if amount:
                    totals[(year, month, "income", "grants_schemes")] += amount

    farm_summary = filtered_raw.get("farm_summary") or {}
    loan_monthly = _loan_monthly_total(farm_summary)
    if loan_monthly:
        for row in combined:
            totals[(row["year"], row["month"], "expense", "loan_repayments")] += loan_monthly

    return {key: round(value, 2) for key, value in totals.items()}


def window_months(filtered_raw: dict, months: int = 12) -> list[tuple[int, int]]:
    """The (year, month) tuples this farm actually has actual data for, in
    the trailing `months` window - the shared definition of "the window"
    for both dataset and manual-record monthly aggregation.
    """
    combined, _ = get_sector_monthly_history(filtered_raw, months=months)
    return [(row["year"], row["month"]) for row in combined]


def build_income_expense_summary(
    farm_file: str,
    sectors: list[str],
    filtered_raw: dict | None = None,
    months: int = 12,
) -> dict:
    """Full Income & Expenses page payload."""
    filtered = filtered_raw or get_selected_sector_data(farm_file, sectors)
    income_rows, expense_rows = _dataset_category_breakdown(filtered, months=months)
    income_total = round(sum(r["total"] for r in income_rows), 2)
    expense_total = round(sum(r["total"] for r in expense_rows), 2)

    selected = filtered.get("selected_sectors") or sectors or []
    manual_records = list_financial_records(farm_file, sectors=selected)
    manual_income_total, manual_expense_total = manual_totals(manual_records)
    income_choices, expense_choices = category_choices_payload()

    return {
        "success": True,
        "farm_name": filtered.get("farm_name", "Farm"),
        "selected_sectors": selected,
        "period": trailing_12_months(),
        "income_total": income_total,
        "expense_total": expense_total,
        "difference": round(income_total - expense_total, 2),
        "income_categories": income_rows,
        "expense_categories": expense_rows,
        "manual_income_total": manual_income_total,
        "manual_expense_total": manual_expense_total,
        "manual_records": manual_records[:20],
        "income_category_choices": income_choices,
        "expense_category_choices": expense_choices,
    }
