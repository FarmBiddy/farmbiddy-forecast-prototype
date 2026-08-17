"""
Executive dashboard summary helpers.

Aggregates multi-sector farm data for the slim dashboard view.
All calculations run on the backend; the frontend renders summaries only.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from forecast_engine.alerts import generate_alerts
from forecast_engine.costs import calculate_costs
from forecast_engine.data_quality import build_data_quality_warnings
from forecast_engine.formatting import format_currency, format_percent
from forecast_engine.health_score import calculate_health_score
from forecast_engine.period_labels import (
    forecast_window,
    historical_month,
    point_in_time,
    trailing_12_months,
)
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from models.multi_sector_farm import (
    SECTOR_LABELS,
    VALID_SECTORS,
    build_debt_register,
    compute_household_month,
)
from services.multi_sector_farm import (
    aggregate_sector_financials,
    filter_farm_by_sectors,
    load_multi_sector_farm,
)
from services.financial_record_service import list_financial_records

ALERT_PRIORITY = {
    "negative profit": 1,
    "increasing overdraft use": 1,
    "negative monthly cashflow": 2,
    "cash-flow warning": 2,
    "insufficient cash for direct debits": 2,
    "low cash balance": 3,
    "loan repayments due in a low-cash month": 3,
    "low profit margin": 4,
    "high feed cost": 5,
}

# What/cause/review reference text for each known alert type (Phase 8). Reuses
# the plain-language reasoning already produced by the Phase 4 classifier and
# Phase 6 early-warning scan rather than inventing a second explanation path;
# "when" is derived per-message below since most of these are month-specific.
ALERT_DETAILS = {
    "negative profit": {
        "what": "Forecast annual loss",
        "cause": "Annual costs are projected to exceed annual revenue on current assumptions.",
        "review": "Review cost assumptions, output volumes, and pricing for the year ahead.",
    },
    "increasing overdraft use": {
        "what": "Overdraft use is widening, not stabilising",
        "cause": "The projected cash balance has worsened for several consecutive months.",
        "review": "Investigate whether the shortfall is short-term or ongoing, and test the practical cash-flow actions under What If?.",
    },
    "negative monthly cashflow": {
        "what": "Monthly income is not covering monthly costs",
        "cause": "Average monthly cash inflows are below average monthly outflows.",
        "review": "Review the timing of major costs and test the cash-flow actions under What If?.",
    },
    "cash-flow warning": {
        "what": "Future months show a negative cash balance",
        "cause": "Projected outgoings exceed projected income in the affected month(s).",
        "review": "Plan ahead for the shortfall — bring forward income, defer costs, or arrange short-term credit.",
    },
    "insufficient cash for direct debits": {
        "what": "Balance may not cover that month's fixed commitments",
        "cause": "Loan repayments and/or household costs due that month exceed the projected balance.",
        "review": "Check direct debit and standing order dates against expected income timing for that month.",
    },
    "low cash balance": {
        "what": "Cash buffer is thin",
        "cause": "The lowest projected cash balance falls below one month of operating costs.",
        "review": "Build a stronger cash reserve before taking on new spending or credit.",
    },
    "loan repayments due in a low-cash month": {
        "what": "Loan repayments land in an already low-cash month",
        "cause": "A scheduled loan repayment coincides with a month where cash is tight.",
        "review": "Consider the 'adjust loan timing' action under What If?.",
    },
    "low profit margin": {
        "what": "Profit margin is below target",
        "cause": "Profit margin is under the 15% threshold considered healthy for this farm type.",
        "review": "Review the biggest cost lines relative to revenue, and pricing or contract terms.",
    },
    "high feed cost": {
        "what": "Feed costs are a high share of revenue",
        "cause": "Feed spend exceeds 35% of revenue, above the recommended range.",
        "review": "Review feed supplier contracts, ration efficiency, and grazing plans.",
    },
}

_MONTH_SPAN_RE = re.compile(r"months? (\d+)(?:-(\d+))?", re.IGNORECASE)
_CONSECUTIVE_RE = re.compile(r"(\d+) consecutive\s+months? starting month (\d+)", re.IGNORECASE)


def _alert_when(message: str) -> str:
    """Best-effort "when this applies" label, parsed from the alert text.

    Falls back to describing the whole forecast window for annual-level
    alerts (negative profit, low margin, etc.) that have no specific month.
    """
    consecutive = _CONSECUTIVE_RE.search(message)
    if consecutive:
        length, start = consecutive.groups()
        return f"Month {start} onward ({length} months)"
    span = _MONTH_SPAN_RE.search(message)
    if span:
        start, end = span.groups()
        return f"Month {start}" if not end or end == start else f"Months {start}-{end}"
    return "Across the current 12-month forecast"


def _alert_details(message: str) -> dict:
    lower = message.lower()
    for keyword, details in ALERT_DETAILS.items():
        if keyword in lower:
            return details
    headline = message.split(":", 1)[0].strip() if ":" in message else message
    return {
        "what": headline,
        "cause": "See the alert message for the underlying figures.",
        "review": "Review the affected figures in Forecasts or Farm Data.",
    }


def get_selected_sector_data(farm_file: str, sectors: list[str]) -> dict:
    """Load multi-sector JSON filtered to the selected sectors."""
    raw = load_multi_sector_farm(farm_file)
    return filter_farm_by_sectors(raw, sectors)


def aggregate_selected_sectors(filtered: dict) -> dict:
    """Aggregate trailing-12-month financials for selected sectors."""
    return aggregate_sector_financials(filtered)


def sum_loan_principal(farm_summary: dict) -> float:
    loans = (farm_summary or {}).get("loans") or []
    return sum(float(loan.get("principal") or 0) for loan in loans)


def sum_outstanding_debt(debt_register: list[dict] | None) -> float:
    """Total outstanding balance across the per-lender debt register."""
    return sum(float(loan.get("outstanding_balance") or 0) for loan in (debt_register or []))


def _debt_outstanding(farm: dict) -> float:
    """Prefer the per-lender debt register; fall back to summed loan principal."""
    debt_register = farm.get("_debt_register")
    if debt_register is not None:
        return sum_outstanding_debt(debt_register)
    return sum_loan_principal({"loans": farm.get("_loans") or []})


def sector_status_label(selected_sectors: list[str]) -> str:
    labels = [SECTOR_LABELS.get(s, s.title()) for s in selected_sectors]
    if len(labels) == len(VALID_SECTORS):
        return "Combined Overview"
    if len(labels) == 1:
        return f"{labels[0]} Only"
    return " + ".join(labels) + " Overview"


def build_overview_header(
    profile: dict,
    selected_sectors: list[str],
    generated_at: str | None,
) -> dict:
    return {
        "farm_name": profile.get("farm_name", "My Farm"),
        "owner_name": profile.get("owner_name", "Farmer"),
        "selected_sectors": selected_sectors,
        "sector_labels": [SECTOR_LABELS.get(s, s.title()) for s in selected_sectors],
        "status_label": sector_status_label(selected_sectors),
        "last_updated": (generated_at or profile.get("last_updated", ""))[:10],
        "location": profile.get("location", ""),
    }


def _margin_status(margin_pct: float) -> str:
    if margin_pct >= 15:
        return "Good"
    if margin_pct >= 8:
        return "Fair"
    return "Watch"


def _status_colour(status: str) -> str:
    mapping = {
        "Good": "green",
        "Fair": "amber",
        "Watch": "amber",
        "Tight": "red",
        "Weak": "red",
        "Negative": "red",
        "High": "red",
        "Moderate": "amber",
        "Low": "green",
        "Medium": "amber",
    }
    return mapping.get(status, "amber")


def calculate_dashboard_kpis(
    forecast_summary: dict,
    farm: dict,
    monthly_forecast: list[dict],
    risk_level: str,
) -> list[dict]:
    """Six executive KPI cards for the dashboard."""
    revenue = float(forecast_summary.get("annual_revenue") or 0)
    profit = float(forecast_summary.get("annual_profit") or 0)
    margin = float(forecast_summary.get("profit_margin") or 0)
    debt = _debt_outstanding(farm)

    cash = float(farm.get("opening_cash_balance") or 0)
    if monthly_forecast:
        cash = float(monthly_forecast[-1].get("running_balance") or cash)

    ttm = trailing_12_months()
    now = point_in_time()

    return [
        {
            "id": "revenue",
            "title": "Revenue",
            "value": format_currency(revenue),
            "subtitle": "Trailing 12 months (annualised)",
            "trend": "up" if revenue > 0 else "neutral",
            "period": ttm,
        },
        {
            "id": "operating_profit",
            "title": "Operating Profit",
            "value": format_currency(profit),
            "subtitle": "After operating costs",
            "trend": "up" if profit > 0 else "down",
            "period": ttm,
        },
        {
            "id": "cash_available",
            "title": "Cash Available",
            "value": format_currency(cash),
            "subtitle": "Projected year-end balance",
            "trend": "up" if cash > 0 else "down",
            "period": now,
        },
        {
            "id": "debt_outstanding",
            "title": "Debt Outstanding",
            "value": format_currency(debt),
            "subtitle": "Estimated outstanding balance across all loans",
            "trend": "neutral",
            "period": now,
        },
        {
            "id": "profit_margin",
            "title": "Profit Margin",
            "value": format_percent(margin),
            "subtitle": _margin_status(margin),
            "trend": "up" if margin >= 15 else ("neutral" if margin >= 8 else "down"),
            "period": ttm,
        },
        {
            "id": "risk_rating",
            "title": "Risk Rating",
            "value": risk_level or "Low",
            "subtitle": "Stable" if risk_level == "Low" else "Monitor closely",
            "trend": "neutral",
            "period": now,
        },
    ]


def calculate_sector_performance(filtered: dict) -> list[dict]:
    """Per-sector trailing-12 revenue, profit, margin, and status."""
    rows: list[dict] = []
    selected = filtered.get("selected_sectors") or []

    for sector_id in selected:
        sector_data = (filtered.get("sectors") or {}).get(sector_id) or {}
        monthly = (sector_data.get("monthly") or [])[-12:]
        revenue = sum(float((m.get("revenue") or {}).get("total") or 0) for m in monthly)
        costs = sum(float((m.get("costs") or {}).get("total") or 0) for m in monthly)
        profit = revenue - costs
        margin = (profit / revenue * 100) if revenue else 0
        status = _margin_status(margin)
        rows.append({
            "sector": sector_id,
            "label": SECTOR_LABELS.get(sector_id, sector_id.title()),
            "revenue": round(revenue, 0),
            "profit": round(profit, 0),
            "margin_pct": round(margin, 1),
            "status": status,
            "period": trailing_12_months(),
        })
    return rows


def calculate_financial_health_snapshot(
    forecast_summary: dict,
    farm: dict,
    kpis_block: dict,
    risk_level: str,
) -> list[dict]:
    """Compact coloured health indicators for the executive dashboard.

    Profitability, cash flow, leverage, and overall health all come from
    the single canonical `calculate_health_score` formula (Phase 7) so this
    snapshot can never disagree with Farm Intelligence or the advisor.
    Liquidity and working capital have no equivalent in that formula and
    stay locally computed.
    """
    opening = float(farm.get("opening_cash_balance") or 0)
    debtors = float(farm.get("debtors") or 0)
    creditors = float(farm.get("creditors") or 0)
    working_capital = debtors - creditors

    health = calculate_health_score({
        "profit_margin": forecast_summary.get("profit_margin"),
        "risk_level": risk_level,
        "feed_cost_ratio": kpis_block.get("feed_cost_ratio"),
        "monthly_cashflow": kpis_block.get("monthly_cashflow"),
        "annual_revenue": forecast_summary.get("annual_revenue"),
        "annual_costs": forecast_summary.get("annual_costs"),
    }, farm)

    liquidity = "Good" if opening >= 20000 else ("Fair" if opening >= 10000 else "Tight")
    wc_status = "Good" if working_capital >= 0 else "Tight"
    overall = (
        "Good" if health["label"] in ("Excellent", "Good")
        else "Fair" if health["label"] == "Fair"
        else "Watch"
    )

    indicators = [
        ("liquidity", "Liquidity", liquidity),
        ("profitability", "Profitability", health["profitability"]),
        ("leverage", "Leverage", health["debt_pressure"]),
        ("cash_flow", "Cash Flow", health["cashflow"]),
        ("working_capital", "Working Capital", wc_status),
        ("overall_health", "Overall Health", overall),
    ]
    return [
        {"key": key, "label": label, "status": status, "colour": _status_colour(status)}
        for key, label, status in indicators
    ]


def _alert_priority(message: str) -> int:
    lower = message.lower()
    for keyword, priority in ALERT_PRIORITY.items():
        if keyword in lower:
            return priority
    return 10


def generate_dashboard_alerts(
    farm: dict,
    forecast_summary: dict,
    kpis_block: dict,
    limit: int = 5,
    monthly_forecast: list[dict] | None = None,
    debt_register: list[dict] | None = None,
) -> list[dict]:
    """Prioritised alerts for the executive dashboard (max 5)."""
    revenue = float(forecast_summary.get("annual_revenue") or 0)
    costs = float(forecast_summary.get("annual_costs") or 0)
    profit = float(forecast_summary.get("annual_profit") or 0)
    monthly_cf = float(kpis_block.get("monthly_cashflow") or 0)

    raw_alerts = generate_alerts(
        farm, profit, revenue, costs, monthly_cf,
        monthly_forecast=monthly_forecast, debt_register=debt_register,
    )
    if not raw_alerts:
        return [{
            "message": "No critical alerts — farm metrics look stable.",
            "severity": "info",
            "priority": 99,
            "what": "No critical alerts",
            "when": "Across the current 12-month forecast",
            "cause": "All monitored figures are within normal ranges.",
            "review": "No action needed — recheck after your next analysis run.",
        }]

    enriched = []
    for msg in raw_alerts:
        priority = _alert_priority(msg)
        severity = "high" if priority <= 3 else ("medium" if priority <= 5 else "low")
        details = _alert_details(msg)
        enriched.append({
            "message": msg,
            "severity": severity,
            "priority": priority,
            "what": details["what"],
            "when": _alert_when(msg),
            "cause": details["cause"],
            "review": details["review"],
        })

    enriched.sort(key=lambda a: a["priority"])
    return enriched[:limit]


def get_sector_monthly_history(filtered: dict, months: int = 24) -> tuple[list[dict], dict[str, list[dict]]]:
    """Combined and per-sector monthly revenue/cost series (last N months)."""
    combined: dict[tuple[int, int], dict] = defaultdict(lambda: {"revenue": 0.0, "costs": 0.0})
    per_sector: dict[str, list[dict]] = {}

    for sector_id, sector_data in (filtered.get("sectors") or {}).items():
        entries = (sector_data.get("monthly") or [])[-months:]
        sector_rows = []
        for entry in entries:
            year = int(entry.get("year") or 0)
            month = int(entry.get("month") or 0)
            rev = float((entry.get("revenue") or {}).get("total") or 0)
            cost = float((entry.get("costs") or {}).get("total") or 0)
            period = entry.get("period") or f"{year}-{month:02d}"
            sector_rows.append({
                "year": year,
                "month": month,
                "period": period,
                "revenue": round(rev, 2),
                "costs": round(cost, 2),
            })
            combined[(year, month)]["revenue"] += rev
            combined[(year, month)]["costs"] += cost
        per_sector[sector_id] = sector_rows

    combined_rows = []
    for (year, month), values in sorted(combined.items()):
        combined_rows.append({
            "year": year,
            "month": month,
            "period": f"{year}-{month:02d}",
            "revenue": round(values["revenue"], 2),
            "costs": round(values["costs"], 2),
        })
    combined_rows = combined_rows[-months:]
    return combined_rows, per_sector


def build_overview_chart_data(filtered: dict, months: int = 24) -> list[dict]:
    """24-month revenue vs costs for the single dashboard chart."""
    combined, _ = get_sector_monthly_history(filtered, months)
    return combined


def _loan_monthly_total(farm_summary: dict) -> float:
    loans = (farm_summary or {}).get("loans") or []
    return sum(float(loan.get("monthly_repayment") or 0) for loan in loans)


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


def get_budget_entries(farm: dict) -> list[dict]:
    """Raw `cash_flow_budget` entries from the dataset, oldest first."""
    entries = farm.get("cash_flow_budget") or []
    return sorted(entries, key=lambda e: (e.get("year", 0), e.get("month", 0)))


def dataset_coverage_cutoff(filtered_raw: dict) -> tuple[int, int] | None:
    """The last (year, month) the canonical dataset has structured monthly
    figures for, across all sectors.

    This is the boundary used to decide whether a farmer-entered
    `FinancialRecord` (P0.2) is safe to add on top of the dataset's own
    actuals: a record dated at or before this month may already be
    reflected in that dataset's aggregate figures, so it is excluded from
    combined Actuals to avoid double-counting (it still appears in the
    farmer's own manual-entry ledger, see `services/income_expense_service.py`).
    A record dated after it is genuinely new activity the dataset has no
    figure for yet, so it is safe to add in full - see `compute_actual_cash_flow`.
    """
    latest: tuple[int, int] | None = None
    for sector_data in (filtered_raw.get("sectors") or {}).values():
        for entry in sector_data.get("monthly") or []:
            year, month = int(entry.get("year") or 0), int(entry.get("month") or 0)
            if not year or not month:
                continue
            if latest is None or (year, month) > latest:
                latest = (year, month)
    return latest


def _record_year_month(date_str: str | None) -> tuple[int, int] | None:
    if not date_str or len(date_str) < 7:
        return None
    try:
        return int(date_str[0:4]), int(date_str[5:7])
    except ValueError:
        return None


def compute_actual_cash_flow(
    filtered_raw: dict,
    farm_summary: dict,
    months: int = 24,
    farm_file: str | None = None,
) -> dict[tuple, dict]:
    """Actual farm+household cash in/out per (year, month), keyed by period tuple.

    Mirrors the `combined_cashflow` definition from
    `services/multi_sector_farm.py`: sector revenue/costs plus scheme income
    and household income/outgoings for that calendar month, minus loan
    repayments. This is the single source of truth for "actual" cash flow,
    reused by cashflow_budget_service (Budget vs Actual) and the Overview's
    current-period/cash-position figures, so none of them can disagree.

    When `farm_file` is given (P0.4), the farmer's manual `FinancialRecord`
    ledger is folded in for any calendar month *after*
    `dataset_coverage_cutoff` - i.e. real activity the dataset does not (and,
    being a fixed snapshot, cannot yet) contain. This is what lets the
    Overview and Budget vs Actual keep moving forward as a farmer records
    new income/expenses, instead of staying frozen at the dataset's last
    historical month. Records dated at or before the cutoff are
    deliberately NOT added here, since the dataset's monthly figures are
    already-aggregated totals for that month and adding a manual entry on
    top would double-count it.
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

    if not farm_file:
        return actual

    cutoff = dataset_coverage_cutoff(filtered_raw)
    sectors = filtered_raw.get("selected_sectors")
    manual_by_period: dict[tuple, dict] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for record in list_financial_records(farm_file, sectors=sectors):
        year_month = _record_year_month(record.get("date"))
        if year_month is None or (cutoff is not None and year_month <= cutoff):
            continue
        key = "income" if record.get("record_type") == "income" else "expense"
        manual_by_period[year_month][key] += float(record.get("amount") or 0)

    for (year, month), amounts in manual_by_period.items():
        period_key = (year, month)
        if period_key in actual:
            # Cannot happen while manual months are strictly after the
            # dataset's cutoff (dataset months are all <= cutoff by
            # definition) - kept as a conservative, additive fallback only.
            entry = actual[period_key]
            entry["actual_cash_in"] = round(entry["actual_cash_in"] + amounts["income"], 2)
            entry["actual_cash_out"] = round(entry["actual_cash_out"] + amounts["expense"], 2)
            entry["actual_net"] = round(entry["actual_cash_in"] - entry["actual_cash_out"], 2)
            continue

        hh = compute_household_month(household, month)
        scheme_income = _scheme_payment_for_month(filtered_raw, month)
        cash_in = round(amounts["income"] + scheme_income + hh["income"], 2)
        cash_out = round(amounts["expense"] + loan_monthly + hh["outgoings"], 2)
        actual[period_key] = {
            "year": year,
            "month": month,
            "period": f"{year}-{month:02d}",
            "actual_cash_in": cash_in,
            "actual_cash_out": cash_out,
            "actual_net": round(cash_in - cash_out, 2),
        }

    return actual


def build_current_period_summary(filtered_raw: dict | None, farm_file: str | None = None) -> dict | None:
    """Income / Costs / Difference for the most recent actual month (Home Dashboard).

    Uses the same farm+household-aware actual cash-flow definition as
    Budget vs Actual, so "this period" on the Overview can never disagree
    with that page. Returns None when there is no actual data yet.

    Passing `farm_file` (P0.4) lets "most recent" advance past the
    dataset's own last historical month once the farmer has logged newer
    manual income/expense records - see `compute_actual_cash_flow`.
    """
    if not filtered_raw:
        return None
    farm_summary = filtered_raw.get("farm_summary") or {}
    actual_by_period = compute_actual_cash_flow(filtered_raw, farm_summary, months=1, farm_file=farm_file)
    if not actual_by_period:
        return None
    latest = actual_by_period[max(actual_by_period.keys())]
    return {
        "period": historical_month(latest["period"]),
        "income": format_currency(latest["actual_cash_in"]),
        "costs": format_currency(latest["actual_cash_out"]),
        "difference": format_currency(latest["actual_net"]),
        "is_deficit": latest["actual_net"] < 0,
    }


_FORECAST_MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def build_cash_position_series(
    filtered_raw: dict | None,
    farm_enriched: dict,
    monthly_forecast: list[dict],
    history_months: int = 6,
    farm_file: str | None = None,
) -> dict | None:
    """Monthly cash-position series for the Overview's primary chart.

    History (Actual): a reconstructed month-end cash balance for the last
    `history_months`, computed backwards from `opening_cash_balance` (the
    farm's real, current cash position) using each month's real actual net
    cash flow (`compute_actual_cash_flow`). The dataset does not store a
    historical running-balance series, so this is a derivation from real
    monthly cash-flow figures anchored at a known real balance — not an
    invented number.

    Forecast: reuses the running balance already computed by
    `monthly_forecast` (the same series shown on Cash Flow > Forecast), so
    this chart can never disagree with that page. Forecast months are
    labelled by calendar month name only (the engine models a typical
    12-month pattern, not specific future dates), and are kept in a
    separate `forecast` list so the UI can render them as a clearly
    distinct, non-contiguous segment rather than implying they are the
    calendar months immediately following the last actual month.

    Budget: the matching `cash_flow_budget` net figure is attached to each
    historical month only where a budget entry actually exists for it.
    """
    if not filtered_raw:
        return None

    farm_summary = filtered_raw.get("farm_summary") or {}
    actual_by_period = compute_actual_cash_flow(
        filtered_raw, farm_summary, months=max(history_months, 1), farm_file=farm_file,
    )
    budget_net_by_period = {
        (entry.get("year"), entry.get("month")): round(
            float(entry.get("expected_cash_in") or 0) - float(entry.get("expected_cash_out") or 0), 2,
        )
        for entry in get_budget_entries(filtered_raw)
    }

    history_sorted = sorted(actual_by_period.values(), key=lambda e: (e["year"], e["month"]))[-history_months:]

    opening = float(farm_enriched.get("opening_cash_balance") or 0)
    running = opening
    history: list[dict] = []
    for entry in reversed(history_sorted):
        history.append({
            "period": entry["period"],
            "label": historical_month(entry["period"])["label"],
            "series": "actual",
            "closing_balance": round(running, 2),
            "net_cashflow": entry["actual_net"],
            "budget_net": budget_net_by_period.get((entry["year"], entry["month"])),
        })
        running -= entry["actual_net"]
    history.reverse()

    forecast: list[dict] = []
    for point in monthly_forecast or []:
        balance = point.get("combined_running_balance", point.get("running_balance"))
        net = point.get("combined_cashflow", point.get("cashflow"))
        month_no = point.get("month")
        label = (
            _FORECAST_MONTH_NAMES[int(month_no) - 1]
            if isinstance(month_no, int) and 1 <= month_no <= 12
            else f"Month {month_no}"
        )
        forecast.append({
            "period": f"forecast-{month_no}",
            "label": label,
            "series": "forecast",
            "closing_balance": round(float(balance), 2) if balance is not None else None,
            "net_cashflow": round(float(net), 2) if net is not None else None,
            "budget_net": None,
        })

    return {
        "current_balance": round(opening, 2),
        "history": history,
        "forecast": forecast,
        "has_budget_reference": any(pt.get("budget_net") is not None for pt in history),
    }


def build_overview_summary(
    farm: dict,
    monthly_forecast: list[dict],
    alerts: list[dict],
    forecast_summary: dict | None = None,
    filtered_raw: dict | None = None,
    farm_file: str | None = None,
) -> dict:
    """The headline figures for the reworked Overview page (UX items 1/9):
    position, trajectory, concern, and next step, all in one place, so a
    farmer never has to hunt across sections just to answer "how am I doing
    and what should I do about it?"

    Reuses the already-computed alerts (Phase 8's `what`/`review` fields)
    rather than re-deriving "concern" and "next action" independently, so
    the Overview can never disagree with the Action Plan's own alert list.
    """
    opening = float(farm.get("opening_cash_balance") or 0)

    top_alert = (alerts or [{}])[0]
    no_critical = top_alert.get("severity") == "info"

    current_period = build_current_period_summary(filtered_raw, farm_file=farm_file)
    cash_position = build_cash_position_series(filtered_raw, farm, monthly_forecast, farm_file=farm_file)
    annual_profit = (forecast_summary or {}).get("annual_profit")
    expected_annual_farm_profit = {
        "value": format_currency(annual_profit) if annual_profit is not None else "—",
        "is_deficit": bool(annual_profit is not None and annual_profit < 0),
        "period": trailing_12_months(),
    }

    if not monthly_forecast:
        return {
            "current_cash_position": {"value": format_currency(opening), "period": point_in_time()},
            "lowest_projected_cash_balance": {"value": format_currency(opening), "month": None},
            "projected_annual_cashflow": {"value": format_currency(0), "period": forecast_window()},
            "main_financial_concern": "Not enough data yet — run an analysis to see this farm's outlook.",
            "recommended_next_action": "Complete the farm data and run an analysis.",
            "current_period": current_period,
            "expected_annual_farm_profit": expected_annual_farm_profit,
            "cash_position": cash_position,
        }

    worst = min(
        monthly_forecast,
        key=lambda m: m.get("combined_running_balance", m.get("running_balance", 0)),
    )
    lowest_balance = float(worst.get("combined_running_balance", worst.get("running_balance", 0)))
    annual_cashflow = sum(
        float(m.get("combined_cashflow", m.get("cashflow", 0))) for m in monthly_forecast
    )

    return {
        "current_cash_position": {
            "value": format_currency(opening),
            "period": point_in_time(),
        },
        "lowest_projected_cash_balance": {
            "value": format_currency(lowest_balance),
            "month": worst.get("month"),
            "month_label": f"Month {worst.get('month')}" if worst.get("month") else "—",
            "is_deficit": lowest_balance < 0,
        },
        "projected_annual_cashflow": {
            "value": format_currency(annual_cashflow),
            "is_deficit": annual_cashflow < 0,
            "period": forecast_window(),
        },
        "main_financial_concern": (
            "No critical concerns — farm metrics look stable."
            if no_critical else top_alert.get("what") or top_alert.get("message", "")
        ),
        "recommended_next_action": (
            "No action needed — recheck after your next analysis run."
            if no_critical else top_alert.get("review") or "Review the alert in the Action Plan section."
        ),
        "current_period": current_period,
        "expected_annual_farm_profit": expected_annual_farm_profit,
        "cash_position": cash_position,
    }


def _latest_period(filtered: dict) -> str | None:
    """Most recent "YYYY-MM" period found across all sectors' monthly entries."""
    periods = [
        entry.get("period")
        for sector_data in (filtered.get("sectors") or {}).values()
        for entry in (sector_data.get("monthly") or [])
        if entry.get("period")
    ]
    return max(periods) if periods else None


def build_executive_dashboard(
    farm_file: str,
    selected_sectors: list[str],
    profile: dict,
    forecast: dict,
    farm: dict,
    filtered_raw: dict,
) -> dict:
    """Assemble the full executive dashboard payload."""
    summary = forecast.get("forecast_summary") or {}
    monthly_forecast = forecast.get("monthly_forecast") or []
    kpis_block = forecast.get("kpis") or {}
    generated_at = forecast.get("generated_at")

    farm_summary = (filtered_raw.get("farm_summary") or {})
    debt_register = farm.get("debt_register") or build_debt_register(farm_summary.get("loans") or [])
    farm_enriched = {
        **farm,
        "debtors": farm_summary.get("debtors", 0),
        "creditors": farm_summary.get("creditors", 0),
        "_loans": farm_summary.get("loans") or [],
        "_debt_register": debt_register,
    }

    alerts = generate_dashboard_alerts(
        farm, summary, kpis_block,
        monthly_forecast=monthly_forecast, debt_register=debt_register,
    )

    return {
        "overview_header": build_overview_header(profile, selected_sectors, generated_at),
        "overview_summary": build_overview_summary(
            farm_enriched, monthly_forecast, alerts,
            forecast_summary=summary, filtered_raw=filtered_raw, farm_file=farm_file,
        ),
        "executive_kpis": calculate_dashboard_kpis(
            summary, farm_enriched, monthly_forecast, forecast.get("risk_level", "Low"),
        ),
        "health_snapshot": calculate_financial_health_snapshot(
            summary, farm_enriched, kpis_block, forecast.get("risk_level", "Low"),
        ),
        "health_score": calculate_health_score({
            "profit_margin": summary.get("profit_margin"),
            "risk_level": forecast.get("risk_level", "Low"),
            "feed_cost_ratio": kpis_block.get("feed_cost_ratio"),
            "monthly_cashflow": kpis_block.get("monthly_cashflow"),
            "annual_revenue": summary.get("annual_revenue"),
            "annual_costs": summary.get("annual_costs"),
        }, farm_enriched),
        "sector_performance": calculate_sector_performance(filtered_raw),
        "alerts": alerts,
        "overview_chart": build_overview_chart_data(filtered_raw),
        "forecast_summary": summary,
        "debt_register": debt_register,
        "data_quality_warnings": build_data_quality_warnings(
            farm_enriched, profile, summary,
            monthly_forecast=monthly_forecast,
            debt_register=debt_register,
            latest_period=_latest_period(filtered_raw),
        ),
    }


def get_historical_data(farm_file: str, sectors: list[str]) -> dict:
    """Full historical monthly data for the Historical Data page."""
    filtered = get_selected_sector_data(farm_file, sectors)
    combined, per_sector = get_sector_monthly_history(filtered, months=24)
    sector_tables = []
    for sector_id in filtered.get("selected_sectors") or []:
        rows = per_sector.get(sector_id) or []
        totals = {
            "revenue": sum(r["revenue"] for r in rows),
            "costs": sum(r["costs"] for r in rows),
            "profit": sum(r["revenue"] - r["costs"] for r in rows),
        }
        sector_tables.append({
            "sector": sector_id,
            "label": SECTOR_LABELS.get(sector_id, sector_id.title()),
            "monthly": rows,
            "totals": totals,
        })
    return {
        "success": True,
        "farm_name": filtered.get("farm_name", "Farm"),
        "selected_sectors": filtered.get("selected_sectors") or [],
        "combined_monthly": combined,
        "sectors": sector_tables,
    }


def calculate_preview_kpis(farm: dict, filtered_raw: dict) -> list[dict]:
    """Executive KPI placeholders for dashboard preview before analysis completes."""
    revenue = calculate_revenue(farm)
    costs = calculate_costs(farm)
    profit = calculate_profit(revenue, costs)
    margin = (profit / revenue * 100) if revenue else 0
    farm_summary = filtered_raw.get("farm_summary") or {}
    summary = {
        "annual_revenue": revenue,
        "annual_profit": profit,
        "profit_margin": margin,
        "annual_costs": costs,
    }
    return calculate_dashboard_kpis(
        summary,
        {
            **farm,
            "debtors": farm_summary.get("debtors", 0),
            "creditors": farm_summary.get("creditors", 0),
            "_loans": farm_summary.get("loans") or [],
            "_debt_register": build_debt_register(farm_summary.get("loans") or []),
        },
        [],
        "Low",
    )
