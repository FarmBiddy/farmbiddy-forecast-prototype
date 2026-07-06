"""
Executive dashboard summary helpers.

Aggregates multi-sector farm data for the slim dashboard view.
All calculations run on the backend; the frontend renders summaries only.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from forecast_engine.alerts import generate_alerts
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from models.multi_sector_farm import SECTOR_LABELS, VALID_SECTORS
from services.multi_sector_farm import (
    aggregate_sector_financials,
    filter_farm_by_sectors,
    load_multi_sector_farm,
)

ALERT_PRIORITY = {
    "negative profit": 1,
    "negative monthly cashflow": 2,
    "low cash balance": 3,
    "low profit margin": 4,
    "high feed cost": 5,
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
        "High": "red",
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
    debt = sum_loan_principal({"loans": farm.get("_loans") or []})

    cash = float(farm.get("opening_cash_balance") or 0)
    if monthly_forecast:
        cash = float(monthly_forecast[-1].get("running_balance") or cash)

    return [
        {
            "id": "revenue",
            "title": "Revenue",
            "value": f"€{revenue:,.0f}",
            "subtitle": "Trailing 12 months (annualised)",
            "trend": "up" if revenue > 0 else "neutral",
        },
        {
            "id": "operating_profit",
            "title": "Operating Profit",
            "value": f"€{profit:,.0f}",
            "subtitle": "After operating costs",
            "trend": "up" if profit > 0 else "down",
        },
        {
            "id": "cash_available",
            "title": "Cash Available",
            "value": f"€{cash:,.0f}",
            "subtitle": "Projected year-end balance",
            "trend": "up" if cash > 0 else "down",
        },
        {
            "id": "debt_outstanding",
            "title": "Debt Outstanding",
            "value": f"€{debt:,.0f}",
            "subtitle": "Total loan principal",
            "trend": "neutral",
        },
        {
            "id": "profit_margin",
            "title": "Profit Margin",
            "value": f"{margin:.1f}%",
            "subtitle": _margin_status(margin),
            "trend": "up" if margin >= 15 else ("neutral" if margin >= 8 else "down"),
        },
        {
            "id": "risk_rating",
            "title": "Risk Rating",
            "value": risk_level or "Low",
            "subtitle": "Stable" if risk_level == "Low" else "Monitor closely",
            "trend": "neutral",
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
        })
    return rows


def calculate_financial_health_snapshot(
    forecast_summary: dict,
    farm: dict,
    kpis_block: dict,
    risk_level: str,
) -> list[dict]:
    """Compact coloured health indicators for the executive dashboard."""
    margin = float(forecast_summary.get("profit_margin") or 0)
    revenue = float(forecast_summary.get("annual_revenue") or 0)
    monthly_cf = float(kpis_block.get("monthly_cashflow") or 0)
    opening = float(farm.get("opening_cash_balance") or 0)

    debtors = float(farm.get("debtors") or 0)
    creditors = float(farm.get("creditors") or 0)
    debt = sum_loan_principal({"loans": farm.get("_loans") or []})

    leverage_ratio = (debt / revenue) if revenue else 0
    working_capital = debtors - creditors

    liquidity = "Good" if opening >= 20000 else ("Fair" if opening >= 10000 else "Tight")
    profitability = _margin_status(margin)
    leverage = "Good" if leverage_ratio < 0.5 else ("Fair" if leverage_ratio < 1.0 else "High")
    cash_flow = "Good" if monthly_cf >= 2000 else ("Fair" if monthly_cf >= 0 else "Tight")
    wc_status = "Good" if working_capital >= 0 else "Tight"

    risk_score = {"Low": 78, "Medium": 58, "High": 35}.get(risk_level or "", 65)
    overall = "Good" if risk_score >= 70 else ("Fair" if risk_score >= 50 else "Watch")

    indicators = [
        ("liquidity", "Liquidity", liquidity),
        ("profitability", "Profitability", profitability),
        ("leverage", "Leverage", leverage),
        ("cash_flow", "Cash Flow", cash_flow),
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
) -> list[dict]:
    """Prioritised alerts for the executive dashboard (max 5)."""
    revenue = float(forecast_summary.get("annual_revenue") or 0)
    costs = float(forecast_summary.get("annual_costs") or 0)
    profit = float(forecast_summary.get("annual_profit") or 0)
    monthly_cf = float(kpis_block.get("monthly_cashflow") or 0)

    raw_alerts = generate_alerts(farm, profit, revenue, costs, monthly_cf)
    if not raw_alerts:
        return [{
            "message": "No critical alerts — farm metrics look stable.",
            "severity": "info",
            "priority": 99,
        }]

    enriched = []
    for msg in raw_alerts:
        priority = _alert_priority(msg)
        severity = "high" if priority <= 3 else ("medium" if priority <= 5 else "low")
        enriched.append({"message": msg, "severity": severity, "priority": priority})

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
    farm_enriched = {
        **farm,
        "debtors": farm_summary.get("debtors", 0),
        "creditors": farm_summary.get("creditors", 0),
        "_loans": farm_summary.get("loans") or [],
    }

    return {
        "overview_header": build_overview_header(profile, selected_sectors, generated_at),
        "executive_kpis": calculate_dashboard_kpis(
            summary, farm_enriched, monthly_forecast, forecast.get("risk_level", "Low"),
        ),
        "health_snapshot": calculate_financial_health_snapshot(
            summary, farm_enriched, kpis_block, forecast.get("risk_level", "Low"),
        ),
        "sector_performance": calculate_sector_performance(filtered_raw),
        "alerts": generate_dashboard_alerts(farm, summary, kpis_block),
        "overview_chart": build_overview_chart_data(filtered_raw),
        "forecast_summary": summary,
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
        },
        [],
        "Low",
    )
