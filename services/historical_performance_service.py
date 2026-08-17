"""
Previous Performance: year-over-year comparison (P1.5).

Answers "how does this year compare to last year?" using the exact same
actuals every other page already relies on - no new financial logic:

  * Income / Costs / Farm profit  -> `services.dashboard_summary.
    get_sector_monthly_history` (sector revenue/costs), the same series the
    Historical Data page and the Overview's 24-month chart already use, with
    the farmer's own manual records folded in for any month past the
    dataset's `dataset_coverage_cutoff` (same rule as below) so these figures
    keep moving forward as a farmer records new entries.
  * Cash generated                -> `services.dashboard_summary.
    compute_actual_cash_flow` (farm + household, after loan repayments,
    folding in the farmer's own P0.2 manual records past the dataset's
    coverage cutoff), the same definition Budget vs Actual and the
    Overview's current-period figures use.

Partial-year handling
----------------------
The dataset (and a farmer's own recent manual entries) will often cover a
calendar year only partly - most obviously the current year in progress.
Comparing a partial year's total against a prior *full* year would
understate this year and mislead the farmer, so:

  * every year in the result is tagged with `months_covered` and
    `is_partial`;
  * a comparison involving a partial year is restricted to whichever
    calendar months both years actually have data for (e.g. Jan-Jun this
    year vs Jan-Jun last year) rather than this year's partial total
    against last year's full-year total, and is tagged
    `basis: "same_months_partial"` with a `note` explaining why;
  * a comparison between two full years is a straightforward total-vs-
    total comparison, tagged `basis: "full_year"`.

Only adjacent years (year vs year-1) are compared - a farmer asking "how
did this year go" cares about the immediately preceding year, not every
possible pair.
"""

from __future__ import annotations

from collections import defaultdict

from services.dashboard_summary import (
    compute_actual_cash_flow,
    dataset_coverage_cutoff,
    get_selected_sector_data,
    get_sector_monthly_history,
)
from services.financial_record_service import list_financial_records

_METRICS = ("income", "costs", "farm_profit", "cash_generated")


def _record_year_month(date_str: str | None) -> tuple[int, int] | None:
    if not date_str or len(date_str) < 7:
        return None
    try:
        return int(date_str[0:4]), int(date_str[5:7])
    except ValueError:
        return None


def _monthly_metric_rows(filtered_raw: dict, farm_file: str | None) -> list[dict]:
    """One row per (year, month) with all four metrics, built from the two
    existing actuals sources plus the farmer's own manual records for any
    month past the dataset's coverage (P0.2/P0.4) - the same
    dataset_coverage_cutoff rule `compute_actual_cash_flow` already uses, so
    a farmer who has been logging 2026 entries sees them reflected here
    exactly as they do everywhere else, never double-counted against the
    dataset's own (necessarily earlier) monthly figures."""
    farm_summary = filtered_raw.get("farm_summary") or {}
    combined_rows, _ = get_sector_monthly_history(filtered_raw, months=10_000)
    actual_cash_flow = compute_actual_cash_flow(filtered_raw, farm_summary, months=10_000, farm_file=farm_file)

    by_period: dict[tuple[int, int], dict] = defaultdict(lambda: {
        "income": 0.0, "costs": 0.0, "farm_profit": 0.0, "cash_generated": 0.0,
    })
    for row in combined_rows:
        key = (row["year"], row["month"])
        by_period[key]["income"] += row["revenue"]
        by_period[key]["costs"] += row["costs"]
        by_period[key]["farm_profit"] += row["revenue"] - row["costs"]

    if farm_file:
        cutoff = dataset_coverage_cutoff(filtered_raw)
        sectors = filtered_raw.get("selected_sectors")
        for record in list_financial_records(farm_file, sectors=sectors):
            year_month = _record_year_month(record.get("date"))
            if year_month is None or (cutoff is not None and year_month <= cutoff):
                continue
            amount = float(record.get("amount") or 0)
            if record.get("record_type") == "income":
                by_period[year_month]["income"] += amount
                by_period[year_month]["farm_profit"] += amount
            else:
                by_period[year_month]["costs"] += amount
                by_period[year_month]["farm_profit"] -= amount

    for (year, month), entry in actual_cash_flow.items():
        by_period[(year, month)]["cash_generated"] += entry["actual_net"]

    return [
        {"year": year, "month": month, **values}
        for (year, month), values in sorted(by_period.items())
    ]


def _sum_rows(rows: list[dict]) -> dict:
    totals = {metric: 0.0 for metric in _METRICS}
    for row in rows:
        for metric in _METRICS:
            totals[metric] += row[metric]
    return {metric: round(value, 2) for metric, value in totals.items()}


def _year_summary(year: int, rows: list[dict]) -> dict:
    months_covered = len({row["month"] for row in rows})
    return {
        "year": year,
        "months_covered": months_covered,
        "is_partial": months_covered < 12,
        **_sum_rows(rows),
    }


def _change(current: float, previous: float) -> dict:
    delta = round(current - previous, 2)
    pct = round((delta / abs(previous)) * 100, 1) if previous else None
    return {"change": delta, "change_pct": pct}


def _build_comparison(
    current_summary: dict,
    previous_summary: dict,
    current_rows: list[dict],
    previous_rows: list[dict],
) -> dict:
    """Compare one year's totals against the year immediately before it,
    restricting to shared calendar months whenever either side is partial."""
    year, previous_year = current_summary["year"], previous_summary["year"]

    if not current_summary["is_partial"] and not previous_summary["is_partial"]:
        current_values, previous_values = current_summary, previous_summary
        comparison = {"year": year, "previous_year": previous_year, "basis": "full_year"}
    else:
        current_months = {row["month"] for row in current_rows}
        previous_months = {row["month"] for row in previous_rows}
        shared_months = current_months & previous_months
        if not shared_months:
            return {
                "year": year,
                "previous_year": previous_year,
                "basis": "no_overlap",
                "note": f"{year} and {previous_year} have no overlapping months of actuals to compare.",
            }
        current_values = _sum_rows([r for r in current_rows if r["month"] in shared_months])
        previous_values = _sum_rows([r for r in previous_rows if r["month"] in shared_months])
        comparison = {
            "year": year,
            "previous_year": previous_year,
            "basis": "same_months_partial",
            "note": (
                f"{year} only has {current_summary['months_covered']} month(s) of actuals so far, "
                f"so this compares the same {len(shared_months)} month(s) of {previous_year} "
                "for a fair like-for-like view."
            ),
        }

    for metric in _METRICS:
        comparison[metric] = {
            "current": current_values[metric],
            "previous": previous_values[metric],
            **_change(current_values[metric], previous_values[metric]),
        }
    return comparison


def build_year_over_year_comparison(farm_file: str, sectors: list[str]) -> dict:
    """Previous Performance payload: one summary row per year of actuals
    available, plus an adjacent-year comparison for each year that has a
    prior year to compare against."""
    filtered_raw = get_selected_sector_data(farm_file, sectors)
    rows = _monthly_metric_rows(filtered_raw, farm_file)

    rows_by_year: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        rows_by_year[row["year"]].append(row)

    years_sorted = sorted(rows_by_year.keys())
    summaries_by_year = {year: _year_summary(year, rows_by_year[year]) for year in years_sorted}

    comparisons = []
    for year in years_sorted:
        previous_year = year - 1
        if previous_year not in summaries_by_year:
            continue
        comparisons.append(_build_comparison(
            summaries_by_year[year], summaries_by_year[previous_year],
            rows_by_year[year], rows_by_year[previous_year],
        ))

    return {
        "success": True,
        "selected_sectors": filtered_raw.get("selected_sectors") or [],
        "years": [summaries_by_year[year] for year in years_sorted],
        "comparisons": comparisons,
    }
