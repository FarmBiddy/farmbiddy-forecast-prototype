"""
FarmBiddy Farmer Edition — professional PDF report generation.

Consumes existing dashboard, forecast, scenario, Monte Carlo, and intelligence
services without modifying the forecast engine.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config.paths import DATASETS_DIR, REPORTS_DIR, ensure_output_dirs
from forecast_engine.alerts import generate_alerts
from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.costs import calculate_costs
from forecast_engine.formatting import format_currency, format_percent
from forecast_engine.monte_carlo import run_monte_carlo
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.scenarios import calculate_scenarios
from models.api_models import ForecastOutputs, SandboxOutputs
from models.multi_sector_farm import SECTOR_LABELS
from services.category_variance_service import build_category_budget_vs_actual
from services.dashboard_summary import (
    calculate_sector_performance,
    generate_dashboard_alerts,
    get_selected_sector_data,
)
from services.farmer_dashboard_service import get_farmer_profile, resolve_farm_file, resolve_sectors
from services.financial_intelligence_service import get_financial_intelligence
from services.forecast_service import run_forecast, run_sandbox_forecast
from services.historical_performance_service import build_year_over_year_comparison
from services.income_expense_service import build_income_expense_summary
from services.loans_service import build_loans_summary
from services.multi_sector_farm import load_farm_for_analysis
from services.scenario_sandbox_service import run_scenario_sandbox

SOFTWARE_VERSION = "1.0.0"

NAVY = colors.HexColor("#0f2744")
GREEN = colors.HexColor("#2d9f5f")
GREEN_LIGHT = colors.HexColor("#e8f7ee")
AMBER = colors.HexColor("#f59e0b")
RED = colors.HexColor("#dc2626")
MUTED = colors.HexColor("#64748b")
WHITE = colors.white

REPORT_TYPES = {
    "executive": "Executive Report",
    "full": "Full Financial Report",
    "scenario": "Scenario Report",
    "investment": "Investment Report",
    "accountant": "Accountant / Advisor Summary",
}

PAGE_SETS: dict[str, list[str]] = {
    "executive": [
        "cover", "executive", "intelligence", "actions", "advisor", "closing",
    ],
    "full": [
        "cover", "executive", "farm", "snapshot", "profitability", "cashflow",
        "forecast", "monte_carlo", "scenarios", "intelligence", "actions",
        "risk_dashboard", "advisor", "action_plan", "investment", "closing",
    ],
    "scenario": [
        "cover", "executive", "scenarios", "risk_dashboard", "actions", "closing",
    ],
    "investment": [
        "cover", "executive", "snapshot", "investment", "advisor", "closing",
    ],
    # Meeting pack for a bank or advisor: Actuals first, then a labelled
    # cash forecast, one milk-price sensitivity, and enterprise contribution.
    # No Monte Carlo, health scores, or investment-readiness theatre.
    "accountant": [
        "cover", "meeting", "farm_position", "income_expenses_actual", "budget_variance",
        "loans_finance", "cash_forecast", "milk_down", "sector_contribution",
        "year_over_year", "closing",
    ],
}


_CALENDAR_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _calendar_month_label(month: Any) -> str:
    try:
        idx = int(month)
        if 1 <= idx <= 12:
            return _CALENDAR_MONTHS[idx - 1]
    except (TypeError, ValueError):
        pass
    return str(month or "—")


def _load_raw_farm(farm_file: str) -> dict:
    path = os.path.join(DATASETS_DIR, farm_file)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _build_farm_position(raw: dict, profile: dict, opening: float) -> dict:
    """Working capital, land, stock and household from the sample dataset."""
    identity = raw.get("identity") or {}
    legal = identity.get("legal_entity") or {}
    farmer = identity.get("farmer") or {}
    location = identity.get("location") or {}
    summary = raw.get("farm_summary") or {}
    scheme = raw.get("scheme_payments") or {}
    dairy_raw = (raw.get("sectors") or {}).get("dairy") or {}
    beef_raw = (raw.get("sectors") or {}).get("beef") or {}
    lamb_raw = (raw.get("sectors") or {}).get("lamb") or {}
    sectors = profile.get("sector_profile") or {}
    dairy = sectors.get("dairy") or {}
    beef = sectors.get("beef") or {}
    lamb = sectors.get("lamb") or {}
    cash = float(summary.get("opening_cash_balance") if summary.get("opening_cash_balance") is not None else opening or 0)
    debtors = float(summary.get("debtors") or 0)
    creditors = float(summary.get("creditors") or 0)
    scheme_months = scheme.get("scheme_payment_months") or {}
    return {
        "legal_name": legal.get("name"),
        "legal_type": legal.get("type"),
        "vat_number": legal.get("vat_number"),
        "registration_number": legal.get("registration_number"),
        "owner_name": farmer.get("name") or profile.get("owner_name"),
        "address": farmer.get("address"),
        "phone": farmer.get("phone"),
        "email": farmer.get("email"),
        "county": location.get("county") or profile.get("county"),
        "herd_number": location.get("herd_number") or profile.get("herd_number"),
        "processor": dairy_raw.get("processor") or profile.get("milk_processor"),
        "total_hectares": summary.get("total_hectares") or profile.get("total_hectares"),
        "land_by_sector": summary.get("land_by_sector") or profile.get("land_by_sector") or {},
        "cash": cash,
        "debtors": debtors,
        "creditors": creditors,
        "working_capital": round(cash + debtors - creditors, 2),
        "supplier_credit": list(summary.get("supplier_credit") or []),
        "household": dict(summary.get("household") or {}),
        "schemes": {
            "biss": scheme.get("biss"),
            "acres": scheme.get("acres"),
            "other_grants": scheme.get("other_grants"),
            "scheme_payment_months": scheme_months,
        },
        "stock": {
            "milking_cows": dairy.get("milking_cows") or (dairy_raw.get("herd") or {}).get("milking_cows"),
            "cattle_on_farm": beef.get("cattle_on_farm") or (beef_raw.get("herd") or {}).get("cattle_on_farm"),
            "ewes": lamb.get("ewes") or (lamb_raw.get("flock") or {}).get("ewes"),
        },
        "notes": summary.get("notes") or "",
    }


def _safe_pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _month_cash(month: dict | None, opening: float = 0) -> float:
    """Farm + household cash when present; else farm-only running balance."""
    if not month:
        return float(opening or 0)
    value = month.get("combined_running_balance")
    if value is None:
        value = month.get("running_balance")
    if value is None:
        return float(opening or 0)
    return float(value)


def _lowest_cash(monthly: list[dict], opening: float = 0) -> dict:
    if not monthly:
        return {"value": float(opening or 0), "month": None, "month_label": "—"}
    worst = min(monthly, key=lambda m: _month_cash(m, opening))
    month = worst.get("month")
    return {
        "value": _month_cash(worst, opening),
        "month": month,
        "month_label": _calendar_month_label(month) if month else "—",
    }


def _period_caption(period: Any) -> str:
    if isinstance(period, dict):
        label = period.get("label") or "Trailing 12 Months"
        start = period.get("start_date")
        end = period.get("end_date")
        if start and end:
            return f"{label} ({start} to {end})"
        return label
    return str(period or "Trailing 12 Months")


def _enterprise_line(selected: list[str]) -> str:
    return " / ".join(SECTOR_LABELS.get(s, s.title()) for s in selected)


def _build_preview_kpis(data: dict) -> list[dict]:
    """Cards for Preview and Generate — never omit numbers after PDF download."""
    if data.get("report_type") == "accountant":
        meeting = data.get("meeting") or {}
        return [
            {"label": "Cash in the model", "value": meeting.get("cash_now"), "kind": "currency"},
            {"label": "Last 12 months net", "value": meeting.get("actual_net"), "kind": "currency"},
            {"label": "Lowest expected cash", "value": meeting.get("lowest_cash"), "kind": "currency"},
            {"label": "Total debt", "value": meeting.get("total_debt"), "kind": "currency"},
        ]
    k = data.get("kpis") or {}
    lowest = data.get("lowest_cash") or {}
    return [
        {"label": "Cash now", "value": k.get("cash_now"), "kind": "currency"},
        {"label": "Lowest expected cash", "value": lowest.get("value"), "kind": "currency"},
        {"label": "Annual profit", "value": k.get("annual_profit"), "kind": "currency"},
        {"label": "Risk level", "value": k.get("risk_level"), "kind": "text"},
    ]


def _risk_light(value: str) -> colors.Color:
    v = (value or "").lower()
    if v in ("good", "low", "strong", "healthy", "positive"):
        return GREEN
    if v in ("fair", "medium", "moderate", "tight", "watch"):
        return AMBER
    return RED


def _scenario_row(farm_file: str, label: str, changes: dict, base: dict) -> dict:
    if not changes:
        return {
            "scenario": label,
            "revenue": base["revenue"],
            "profit": base["profit"],
            "cashflow": base["cashflow"],
            "risk_level": base["risk_level"],
        }
    outputs = SandboxOutputs(forecast_summary=True, risk_level=True, kpis=True)
    try:
        result = run_sandbox_forecast(farm_file, changes, outputs)
        summary = result.get("forecast_summary") or {}
        kpis = result.get("kpis") or {}
        return {
            "scenario": label,
            "revenue": summary.get("annual_revenue", 0),
            "profit": summary.get("annual_profit", 0),
            "cashflow": kpis.get("monthly_cashflow", 0),
            "risk_level": result.get("risk_level", "Medium"),
        }
    except Exception:
        return {
            "scenario": label,
            "revenue": base["revenue"],
            "profit": base["profit"],
            "cashflow": base["cashflow"],
            "risk_level": base["risk_level"],
        }


def _build_scenario_table(farm_file: str, farm: dict, base_risk: str) -> list[dict]:
    revenue = calculate_revenue(farm)
    costs = calculate_costs(farm)
    profit = calculate_profit(revenue, costs)
    monthly_cf = calculate_monthly_cashflow(revenue, costs)
    base = {
        "revenue": round(revenue, 0),
        "profit": round(profit, 0),
        "cashflow": round(monthly_cf, 0),
        "risk_level": base_risk,
    }
    milk = float(farm["milk_price"])
    feed = float(farm["feed"])
    loans = float(farm["loan_repayments"])
    defs = [
        ("Current", {}),
        ("Milk Price +5c/L", {"milk_price": round(milk + 0.05, 4)}),
        ("Milk Price -5c/L", {"milk_price": round(max(milk - 0.05, 0.01), 4)}),
        ("Feed Cost +10%", {"feed": round(feed * 1.10, 2)}),
        ("Feed Cost -10%", {"feed": round(feed * 0.90, 2)}),
        ("Interest Rate +1%", {"loan_repayments": round(loans * 1.01, 2)}),
    ]
    return [_scenario_row(farm_file, label, changes, base) for label, changes in defs]


def _monte_distribution(farm: dict, iterations: int = 500) -> tuple[list[float], dict]:
    """Histogram data for PDF — uses same perturbation logic as the engine."""
    rng = random.Random(42)
    profits: list[float] = []
    base_price = float(farm.get("milk_price", 0.42))
    base_feed = float(farm.get("feed", 0))
    cash_shortages = 0
    opening = float(farm.get("opening_cash_balance", 0))

    for _ in range(iterations):
        scenario = dict(farm)
        scenario["milk_price"] = base_price * rng.uniform(0.90, 1.10)
        scenario["feed"] = base_feed * rng.uniform(0.92, 1.15)
        revenue = calculate_revenue(scenario)
        costs = calculate_costs(scenario)
        profit = calculate_profit(revenue, costs)
        profits.append(profit)
        monthly_cf = calculate_monthly_cashflow(revenue, costs)
        if opening + monthly_cf * 3 < 0:
            cash_shortages += 1

    profits.sort()
    n = len(profits)
    stats = {
        "probability_of_profit": round(sum(1 for p in profits if p >= 0) / n, 4),
        "probability_of_loss": round(sum(1 for p in profits if p < 0) / n, 4),
        "probability_of_cash_shortage": round(cash_shortages / n, 4),
        "confidence_low": round(profits[int(n * 0.10)], 0),
        "confidence_high": round(profits[int(n * 0.90)], 0),
    }
    return profits, stats


def _investment_readiness(forecast: dict, farm: dict, health: dict) -> dict:
    margin = forecast.get("profit_margin", 0)
    monthly_cf = forecast.get("monthly_cashflow", 0)
    opening = farm.get("opening_cash_balance", 0)
    revenue = forecast.get("annual_revenue", 1)
    loan_pct = _safe_pct(farm.get("loan_repayments", 0), revenue)
    risk = forecast.get("risk_level", "Medium")

    scores = {
        "profitability": min(100, max(20, int(margin * 4))),
        "liquidity": 85 if monthly_cf >= 2500 else 65 if monthly_cf >= 0 else 35,
        "debt_capacity": 80 if loan_pct < 10 else 60 if loan_pct < 15 else 40,
        "cash_stability": min(100, max(30, int(opening / max(revenue / 12, 1) * 20))),
        "growth_potential": health.get("score", 70),
        "expansion_readiness": 75 if risk == "Low" and margin >= 12 else 55 if margin >= 8 else 35,
    }
    overall = int(sum(scores.values()) / len(scores))

    if overall >= 80:
        explanation = (
            "Based on current financial performance and projected cashflow, the farm is in a "
            "strong position for moderate expansion. Improving debt capacity before major "
            "investments would further strengthen financial resilience."
        )
    elif overall >= 60:
        explanation = (
            "The farm shows solid fundamentals but should strengthen cash reserves and "
            "debt coverage before significant investment or herd expansion."
        )
    else:
        explanation = (
            "Investment readiness is limited on current figures. Focus on profitability, "
            "cashflow stability, and debt management before major capital projects."
        )

    return {"overall_score": overall, "components": scores, "explanation": explanation}


def _executive_narrative(forecast: dict, health: dict, intel: dict) -> str:
    margin = forecast.get("profit_margin", 0)
    profit = forecast.get("annual_profit", 0)
    risk = forecast.get("risk_level", "Medium")
    cf = health.get("cashflow", "Tight")
    feed = health.get("feed_pressure", "Moderate")

    if profit > 0 and margin >= 15 and risk == "Low":
        opening = (
            "Your farm is currently operating from a strong financial position with healthy "
            "profitability and positive cashflow."
        )
    elif profit > 0:
        opening = (
            "Your farm remains profitable on current assumptions, though some areas need "
            "close monitoring to protect margins."
        )
    else:
        opening = (
            "Your farm faces profitability pressure on current figures and should prioritise "
            "cost control and cash management."
        )

    feed_part = (
        f"Feed costs remain the largest expense to monitor ({feed.lower()} pressure) "
        if feed != "Low"
        else "Feed costs are reasonably controlled "
    )
    outlook = (
        "while current forecasts indicate stable performance over the coming twelve months."
        if risk == "Low"
        else "and scenario testing is recommended before major spending decisions."
    )
    headline = intel.get("advisor_headline", "")
    if headline:
        return f"{opening} {headline}"
    return f"{opening} {feed_part}{outlook}"


def _enhanced_actions(intel: dict, forecast: dict, farm: dict) -> list[dict]:
    actions = []
    feed = forecast.get("feed_cost_ratio", 35)
    for item in intel.get("recommended_actions", [])[:5]:
        title = item.get("title", "")
        reason = item.get("reason", "")
        priority = "High" if any(w in title.lower() for w in ("cash", "debt", "urgent", "loss")) else "Medium"
        benefit = ""
        if "feed" in title.lower():
            benefit = f"{format_currency(farm.get('feed', 0) * 0.05)} annually"
        elif "debt" in title.lower() or "loan" in title.lower():
            benefit = f"{format_currency(farm.get('loan_repayments', 0) * 0.08)} interest savings potential"
        elif "cash" in title.lower():
            benefit = f"{format_currency(max(forecast.get('annual_profit', 0) * 0.05, 5000))} buffer target"
        else:
            benefit = f"{format_currency(max(forecast.get('annual_profit', 0) * 0.03, 3000))} estimated impact"
        actions.append({
            "priority": priority,
            "recommendation": title,
            "estimated_benefit": benefit,
            "reason": reason or "Based on your latest farm forecast.",
            "expected_benefit": "Improved margin resilience and clearer cash planning.",
        })

    if len(actions) < 5:
        defaults = [
            ("Review feed supplier contracts before winter.", "Feed prices may rise seasonally.", f"{format_currency(farm.get('feed', 0) * 0.05)} annually"),
            ("Update financial records monthly.", "Better records improve decision speed.", "Reduced admin cost and fewer surprises"),
            ("Run a new forecast after major changes.", "Keeps plans aligned with reality.", "Better timing for investments"),
            ("Review labour efficiency per cow.", "Labour is a major fixed cost.", f"{format_currency(farm.get('labour', 0) * 0.04)} potential savings"),
        ]
        for rec, reason, benefit in defaults:
            if len(actions) >= 5:
                break
            if not any(rec in a["recommendation"] for a in actions):
                actions.append({
                    "priority": "Medium",
                    "recommendation": rec,
                    "estimated_benefit": benefit,
                    "reason": reason,
                    "expected_benefit": "Stronger day-to-day financial control.",
                })
    return actions[:5]


def _action_plan(intel: dict, actions: list[dict]) -> dict:
    recs = [a["recommendation"] for a in actions]
    weaknesses = intel.get("key_weaknesses", [])
    this_month = recs[:2] or ["Review feed supplier quotes", "Check monthly cash position"]
    next_month = recs[2:4] or ["Run updated forecast", "Review loan repayment schedule"]
    within_90 = recs[4:] + weaknesses[:2] or [
        "Evaluate machinery investment timing",
        "Review labour costs against output",
    ]
    return {
        "this_month": this_month[:3],
        "next_month": next_month[:3],
        "within_90_days": within_90[:4],
    }


def _advisor_page(intel: dict, forecast: dict, health: dict) -> str:
    strengths = intel.get("key_strengths", [])
    risks = intel.get("biggest_risks", [])
    opportunities = intel.get("opportunities", [])
    profit = forecast.get("annual_profit", 0)

    parts = [
        "CURRENT FINANCIAL POSITION\n\n",
        intel.get("plain_summary", ""),
        "\n\nFORECAST OUTLOOK\n\n",
        f"Annual profit is forecast at {format_currency(profit)} with a farm health score of "
        f"{health.get('score', '—')}/100. Risk level is {forecast.get('risk_level', 'Medium')}. ",
        _executive_narrative(forecast, health, intel),
        "\n\nMAIN OPPORTUNITIES\n\n",
        "\n".join(f"• {o}" for o in opportunities[:4]) or "• Maintain cost discipline to create future investment room.",
        "\n\nMAIN RISKS\n\n",
    ]
    if risks:
        parts.append("\n".join(f"• {r.get('driver')}: {r.get('commentary', '')}" for r in risks[:4]))
    else:
        parts.append("• Monitor milk price and feed cost movements regularly.")
    parts.append("\n\nSUGGESTED PRIORITIES\n\n")
    for i, action in enumerate(intel.get("recommended_actions", [])[:3], 1):
        parts.append(f"{i}. {action.get('title', '')}\n")
    return "".join(parts)


def _risk_dashboard(forecast: dict, farm: dict, health: dict) -> list[dict]:
    revenue = forecast.get("annual_revenue", 1)
    margin = forecast.get("profit_margin", 0)
    monthly_cf = forecast.get("monthly_cashflow", 0)
    feed_pct = forecast.get("feed_cost_ratio", 35)
    loan_pct = _safe_pct(farm.get("loan_repayments", 0), revenue)

    def row(name: str, status: str, explanation: str) -> dict:
        return {"name": name, "status": status, "explanation": explanation}

    return [
        row("Liquidity", health.get("cashflow", "Tight"),
            "Based on average monthly cashflow and opening balance."),
        row("Profitability", health.get("profitability", "Fair"),
            f"Profit margin is {format_percent(margin)} on current assumptions."),
        row("Debt", "High" if loan_pct > 15 else "Moderate" if loan_pct > 10 else "Low",
            f"Loan repayments are {format_percent(loan_pct)} of revenue."),
        row("Cashflow", "Negative" if monthly_cf < 0 else "Good" if monthly_cf >= 2000 else "Tight",
            f"Average monthly cashflow is {format_currency(monthly_cf)}."),
        row("Milk Price Exposure", forecast.get("risk_level", "Medium"),
            "Income is sensitive to milk price changes — test scenarios regularly."),
        row("Feed Dependency", health.get("feed_pressure", "Moderate"),
            f"Feed represents {format_percent(feed_pct, decimals=0)} of revenue."),
        row("Operational Efficiency", "Good" if margin >= 12 else "Fair" if margin >= 8 else "Weak",
            "Measured by margin and cost control across the enterprise."),
        row("Expansion Risk", "Low" if health.get("score", 0) >= 75 else "Medium" if health.get("score", 0) >= 55 else "High",
            "Combines profitability, cash, and debt pressure."),
    ]


def collect_report_data(
    farm_id: str | None = None,
    report_type: str = "full",
    report_date: str | None = None,
    sectors: list[str] | None = None,
) -> dict[str, Any]:
    """Gather all modules needed for PDF generation."""
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    farm = load_farm_for_analysis(farm_file, selected)
    profile = get_farmer_profile(farm_id, selected)
    is_accountant = report_type == "accountant"
    intel = {} if is_accountant else get_financial_intelligence(farm_id, sectors=selected)

    outputs = ForecastOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        top_risk_drivers=True,
        advisory_summary=True,
        kpis=True,
        scenarios=True,
    )
    try:
        forecast_run = run_forecast(
            farm_file=farm_file,
            outputs=outputs,
            save_result=False,
            generate_charts=False,
            sectors=selected,
        )
    except Exception:
        revenue = calculate_revenue(farm)
        costs = calculate_costs(farm)
        profit = calculate_profit(revenue, costs)
        margin = (profit / revenue * 100) if revenue else 0
        monthly_cf = calculate_monthly_cashflow(revenue, costs)
        monthly = generate_monthly_forecast(farm, revenue, costs, farm.get("opening_cash_balance", 0))
        alerts = generate_alerts(farm, profit, revenue, costs, monthly_cf)
        forecast_run = {
            "forecast_summary": {
                "farm_name": farm.get("farm_name"),
                "annual_revenue": round(revenue, 2),
                "annual_costs": round(costs, 2),
                "annual_profit": round(profit, 2),
                "profit_margin": round(margin, 2),
            },
            "monthly_forecast": monthly,
            "alerts": alerts,
            "risk_level": calculate_risk_level(alerts, profit / revenue if revenue else 0),
            "kpis": {
                "feed_cost_ratio": _safe_pct(farm.get("feed", 0), revenue),
                "monthly_cashflow": round(monthly_cf, 2),
            },
        }

    summary = forecast_run.get("forecast_summary") or {}
    kpis = forecast_run.get("kpis") or {}
    monthly = forecast_run.get("monthly_forecast") or []
    revenue = summary.get("annual_revenue", 0)
    costs = summary.get("annual_costs", 0)
    profit = summary.get("annual_profit", 0)
    margin = summary.get("profit_margin", 0)
    monthly_cf = kpis.get("monthly_cashflow", calculate_monthly_cashflow(revenue, costs))
    feed_pct = kpis.get("feed_cost_ratio", _safe_pct(farm.get("feed", 0), revenue))
    risk = forecast_run.get("risk_level", "Medium")
    health = intel.get("health_score", {})

    if is_accountant:
        monte: dict[str, Any] = {}
        profits: list[float] = []
        scenarios: list[dict] = []
        forecast_scenarios: list[dict] = []
        investment: dict[str, Any] = {}
        actions: list[dict] = []
        action_plan: dict[str, Any] = {}
        risk_rows: list[dict] = []
    else:
        monte = run_monte_carlo(farm, iterations=1000)
        profits, monte_extra = _monte_distribution(farm)
        monte.update(monte_extra)
        monte["summary"] = (
            f"The simulation indicates a {monte['probability_of_profit'] * 100:.0f}% probability "
            f"that the farm will remain profitable during the next twelve months."
        )
        scenarios = _build_scenario_table(farm_file, farm, risk)
        forecast_scenarios = calculate_scenarios(farm)
        investment = _investment_readiness(
            {
                "annual_revenue": revenue,
                "annual_profit": profit,
                "profit_margin": margin,
                "monthly_cashflow": monthly_cf,
                "risk_level": risk,
                "feed_cost_ratio": feed_pct,
            },
            farm,
            health,
        )
        actions = _enhanced_actions(intel, {**summary, "feed_cost_ratio": feed_pct, "monthly_cashflow": monthly_cf}, farm)
        action_plan = _action_plan(intel, actions)
        risk_rows = _risk_dashboard(
            {**summary, "monthly_cashflow": monthly_cf, "feed_cost_ratio": feed_pct, "risk_level": risk},
            farm,
            health,
        )

    opening = float(farm.get("opening_cash_balance") or 0)
    lowest = _lowest_cash(monthly, opening)

    income_expense_actual = build_income_expense_summary(farm_file, selected)
    budget_variance = build_category_budget_vs_actual(farm_file, selected)
    # build_loans_summary needs the same dict-shaped {what, when, ...} alerts
    # the live dashboard uses to spot a "loan repayment lands in a low-cash
    # month" overlap - the plain-string `forecast_run["alerts"]` below comes
    # from the older forecast_engine.alerts shape and cannot be looked up by
    # `what`, so it is recomputed here exactly as
    # `dashboard_summary.build_executive_dashboard` already does.
    debt_register = farm.get("debt_register") or []
    dashboard_alerts = generate_dashboard_alerts(farm, summary, kpis, monthly_forecast=monthly, debt_register=debt_register)
    loans_summary = build_loans_summary(debt_register, dashboard_alerts)
    year_over_year = build_year_over_year_comparison(farm_file, selected)

    milk_down: dict[str, Any] = {}
    sector_performance: list[dict] = []
    if is_accountant:
        try:
            milk_down = run_scenario_sandbox(
                farm_file, {"milk_price_cents_change": -5}, sectors=selected
            )
        except Exception:
            milk_down = {"success": False, "comparison": {}}
        try:
            sector_performance = calculate_sector_performance(
                get_selected_sector_data(farm_file, selected)
            )
        except Exception:
            sector_performance = []

    period_label = _period_caption(income_expense_actual.get("period"))
    raw_farm = _load_raw_farm(farm_file) if is_accountant else {}
    farm_position = _build_farm_position(raw_farm, profile, opening) if is_accountant else {}
    repay = float(loans_summary.get("total_annual_repayments") or 0)
    actual_net = float(income_expense_actual.get("difference") or 0)
    if actual_net < 0:
        repayment_note = (
            f"Last 12 months net is {format_currency(actual_net)} on recorded figures, "
            f"so it does not cover annual loan repayments of {format_currency(repay)}."
        )
    else:
        repayment_note = (
            f"Last 12 months net is {format_currency(actual_net)} on recorded figures. "
            f"Annual loan repayments are {format_currency(repay)}."
        )
    meeting = {
        "cash_now": opening,
        "actual_income": income_expense_actual.get("income_total", 0),
        "actual_costs": income_expense_actual.get("expense_total", 0),
        "actual_net": actual_net,
        "total_debt": loans_summary.get("total_outstanding_debt", 0),
        "annual_repayments": repay,
        "lowest_cash": lowest["value"],
        "lowest_cash_month": lowest["month"],
        "lowest_cash_month_label": lowest["month_label"],
        "period_label": period_label,
        "enterprises": _enterprise_line(selected),
        "repayment_note": repayment_note,
    }

    if is_accountant:
        executive_summary = (
            f"Unaudited management information for {profile.get('farm_name', 'this farm')} "
            f"covering {period_label}. Not statutory accounts. Cash in the model is the "
            "opening figure in FarmBiddy, not a live bank balance. Last-12-month totals "
            "are recorded. Lowest expected cash is a seasonal forecast."
        )
        advisor_summary = ""
    else:
        executive_summary = _executive_narrative(
            {**summary, "risk_level": risk}, health, intel
        )
        advisor_summary = _advisor_page(intel, {**summary, "risk_level": risk}, health)

    cost_breakdown = {
        "Feed": farm.get("feed", 0),
        "Fertiliser": farm.get("fertiliser", 0),
        "Vet": farm.get("vet", 0),
        "Contractor": farm.get("contractor", 0),
        "Labour": farm.get("labour", 0),
        "Insurance": farm.get("insurance", 0),
        "Loan Repayments": farm.get("loan_repayments", 0),
        "Fuel": farm.get("fuel", 0),
        "Electricity": farm.get("electricity", 0),
    }

    generated = report_date or datetime.now().strftime("%d %B %Y")
    payload = {
        "farm_file": farm_file,
        "farm_name": profile.get("farm_name", farm.get("farm_name")),
        "report_type": report_type,
        "report_type_label": REPORT_TYPES.get(report_type, "Full Financial Report"),
        "report_date": generated,
        "generated_at": datetime.now().isoformat(),
        "software_version": SOFTWARE_VERSION,
        "is_sample_data": bool(profile.get("is_sample_data")),
        "selected_sectors": selected,
        "profile": profile,
        "farm": farm,
        "forecast_summary": summary,
        "monthly_forecast": monthly,
        "lowest_cash": lowest,
        "meeting": meeting,
        "farm_position": farm_position,
        "kpis": {
            "cash_now": opening,
            "cash_available": opening,
            "annual_profit": profit,
            "risk_level": risk,
            "health_score": health.get("score", 70),
            "revenue": revenue,
            "operating_costs": costs,
            "net_profit": profit,
            "debt": loans_summary.get("total_outstanding_debt", farm.get("loan_repayments", 0)),
            "feed_pct": feed_pct,
            "labour_pct": _safe_pct(farm.get("labour", 0), revenue),
            "vet_pct": _safe_pct(farm.get("vet", 0), revenue),
            "electricity_pct": _safe_pct(farm.get("electricity", 0), revenue),
            "fuel_pct": _safe_pct(farm.get("fuel", 0), revenue),
        },
        "cost_breakdown": cost_breakdown,
        "health_score": health,
        "executive_summary": executive_summary,
        "financial_intelligence": intel,
        "monte_carlo": monte,
        "monte_profits": profits,
        "scenarios": scenarios,
        "forecast_scenarios": forecast_scenarios,
        "recommended_actions": actions,
        "action_plan": action_plan,
        "advisor_summary": advisor_summary,
        "risk_dashboard": risk_rows,
        "investment_readiness": investment,
        "alerts": forecast_run.get("alerts", []),
        "income_expense_actual": income_expense_actual,
        "budget_variance": budget_variance,
        "loans_summary": loans_summary,
        "year_over_year": year_over_year,
        "milk_down": milk_down,
        "sector_performance": sector_performance,
        "period_label": period_label,
    }
    payload["preview_kpis"] = _build_preview_kpis(payload)
    return payload


# ---------------------------------------------------------------------------
# Chart generation (matplotlib → temp PNG for ReportLab)
# ---------------------------------------------------------------------------
# Matplotlib is imported lazily. Importing pyplot at module load scans fonts
# on headless Linux and can block Uvicorn from binding a port (Render timeout).

def _pyplot():
    os.environ.setdefault("MPLBACKEND", "Agg")
    cache = os.path.join(
        os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp",
        "farmbiddy-mpl",
    )
    os.environ.setdefault("MPLCONFIGDIR", cache)
    os.makedirs(cache, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _save_chart(fig, prefix: str) -> str:
    plt = _pyplot()
    path = os.path.join(tempfile.gettempdir(), f"farmbiddy_{prefix}_{os.getpid()}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _chart_revenue_costs(monthly: list[dict]) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(8, 4))
    months = [str(m.get("month", i)) for i, m in enumerate(monthly, 1)]
    rev = [m.get("revenue", 0) for m in monthly]
    cost = [m.get("costs", 0) for m in monthly]
    ax.plot(months, rev, color="#2d9f5f", linewidth=2.5, marker="o", label="Revenue")
    ax.plot(months, cost, color="#0f2744", linewidth=2.5, marker="s", label="Costs")
    ax.set_title("Revenue vs Costs", fontsize=14, fontweight="bold", color="#0f2744")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return _save_chart(fig, "rev_cost")


def _chart_cost_breakdown(breakdown: dict) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [k for k, v in breakdown.items() if v]
    values = [v for v in breakdown.values() if v]
    colors_list = ["#2d9f5f", "#0f2744", "#64748b", "#f59e0b", "#1e3a5f", "#94a3b8", "#dc2626", "#4ade80", "#60a5fa"]
    ax.barh(labels, values, color=colors_list[: len(labels)])
    ax.set_title("Cost Breakdown", fontsize=14, fontweight="bold", color="#0f2744")
    fig.tight_layout()
    return _save_chart(fig, "costs")


def _month_axis_labels(monthly: list[dict], calendar_names: bool = False) -> list[str]:
    if calendar_names:
        return [_calendar_month_label(m.get("month", i)) for i, m in enumerate(monthly, 1)]
    return [str(m.get("month", i)) for i, m in enumerate(monthly, 1)]


def _chart_cashflow(monthly: list[dict], calendar_names: bool = False) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(8, 4))
    months = _month_axis_labels(monthly, calendar_names)
    cf = [m.get("combined_cashflow", m.get("cashflow", 0)) for m in monthly]
    colors_bars = ["#2d9f5f" if v >= 0 else "#dc2626" for v in cf]
    ax.bar(months, cf, color=colors_bars)
    ax.axhline(0, color="#64748b", linewidth=0.8)
    ax.set_title("Monthly Cashflow", fontsize=14, fontweight="bold", color="#0f2744")
    fig.tight_layout()
    return _save_chart(fig, "cashflow")


def _chart_reserve(monthly: list[dict], calendar_names: bool = False) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(8, 4))
    months = _month_axis_labels(monthly, calendar_names)
    bal = [_month_cash(m) for m in monthly]
    ax.fill_between(range(len(months)), bal, alpha=0.3, color="#2d9f5f")
    ax.plot(months, bal, color="#0f2744", linewidth=2.5, marker="o")
    ax.set_title("Cash Reserve Trend", fontsize=14, fontweight="bold", color="#0f2744")
    fig.tight_layout()
    return _save_chart(fig, "reserve")


def _chart_forecast_cases(scenarios: list[dict]) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(7, 4))
    names = [s.get("name", "") for s in scenarios]
    profits = [s.get("profit", 0) for s in scenarios]
    ax.bar(names, profits, color=["#2d9f5f", "#0f2744", "#f59e0b"])
    ax.set_title("12-Month Forecast Cases", fontsize=14, fontweight="bold", color="#0f2744")
    plt.xticks(rotation=15, ha="right")
    fig.tight_layout()
    return _save_chart(fig, "forecast_cases")


def _chart_monte(profits: list[float]) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(profits, bins=30, color="#2d9f5f", edgecolor="white", alpha=0.85)
    ax.axvline(sum(profits) / len(profits), color="#0f2744", linestyle="--", label="Expected")
    ax.set_title("Monte Carlo Profit Distribution", fontsize=14, fontweight="bold", color="#0f2744")
    ax.legend()
    fig.tight_layout()
    return _save_chart(fig, "monte")


def _chart_scenarios(scenarios: list[dict]) -> str:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [s["scenario"][:18] for s in scenarios]
    profits = [s["profit"] for s in scenarios]
    ax.bar(labels, profits, color="#0f2744")
    ax.set_title("Scenario Profit Comparison", fontsize=14, fontweight="bold", color="#0f2744")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    fig.tight_layout()
    return _save_chart(fig, "scenarios")


def _generate_report_charts(data: dict) -> dict[str, str]:
    monthly = data.get("monthly_forecast") or []
    if not monthly:
        revenue = data["forecast_summary"].get("annual_revenue", 0)
        costs = data["forecast_summary"].get("annual_costs", 0)
        monthly = [
            {"month": i, "revenue": revenue / 12, "costs": costs / 12,
             "cashflow": (revenue - costs) / 12, "running_balance": data["kpis"].get("cash_now", 0)}
            for i in range(1, 13)
        ]
    if data.get("report_type") == "accountant":
        charts = {}
        if monthly:
            charts["cashflow"] = _chart_cashflow(monthly, calendar_names=True)
            charts["reserve"] = _chart_reserve(monthly, calendar_names=True)
        return charts
    charts = {}
    charts["revenue_costs"] = _chart_revenue_costs(monthly)
    charts["cost_breakdown"] = _chart_cost_breakdown(data["cost_breakdown"])
    charts["cashflow"] = _chart_cashflow(monthly)
    charts["reserve"] = _chart_reserve(monthly)
    charts["forecast_cases"] = _chart_forecast_cases(data.get("forecast_scenarios", []))
    if data.get("monte_profits"):
        charts["monte"] = _chart_monte(data["monte_profits"])
    charts["scenarios"] = _chart_scenarios(data.get("scenarios", []))
    return charts


# ---------------------------------------------------------------------------
# PDF building
# ---------------------------------------------------------------------------

class _ReportDoc(SimpleDocTemplate):
    def __init__(self, filename: str, data: dict, **kwargs):
        self.report_data = data
        super().__init__(filename, **kwargs)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Heading1"], fontSize=18, leading=24,
            textColor=NAVY, spaceBefore=0, spaceAfter=12,
        ),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=16, leading=20, textColor=NAVY, spaceBefore=8, spaceAfter=8),
        "h3": ParagraphStyle("H3", parent=base["Heading3"], fontSize=12, leading=16, textColor=GREEN, spaceAfter=6),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#1a2332")),
        "muted": ParagraphStyle("Muted", parent=base["Normal"], fontSize=9, textColor=MUTED, leading=12),
        "center": ParagraphStyle("Center", parent=base["Normal"], fontSize=10, leading=18, alignment=TA_CENTER, textColor=MUTED, spaceAfter=6),
        "cover_title": ParagraphStyle(
            "CoverTitle", fontName="Helvetica-Bold", fontSize=22, leading=28,
            textColor=NAVY, alignment=TA_CENTER, spaceBefore=0, spaceAfter=12,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", fontName="Helvetica", fontSize=13, leading=20,
            textColor=GREEN, alignment=TA_CENTER, spaceBefore=0, spaceAfter=10,
        ),
        "cover_farm": ParagraphStyle(
            "CoverFarm", fontName="Helvetica-Bold", fontSize=16, leading=22,
            textColor=NAVY, alignment=TA_CENTER, spaceBefore=4, spaceAfter=12,
        ),
        "cover_sample": ParagraphStyle(
            "CoverSample", fontName="Helvetica-Bold", fontSize=10, leading=16,
            alignment=TA_CENTER, textColor=RED, spaceBefore=6, spaceAfter=10,
        ),
    }


def _header_footer(canvas, doc):
    data = doc.report_data
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 18 * mm, w, 18 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(20 * mm, h - 12 * mm, "FarmBiddy")
    canvas.setFont("Helvetica", 8)
    right = data.get("farm_name", "Farm Report") or "Farm Report"
    brand_w = canvas.stringWidth("FarmBiddy", "Helvetica-Bold", 9)
    max_right = w - 44 * mm - brand_w
    if canvas.stringWidth(right, "Helvetica", 8) > max_right:
        while right and canvas.stringWidth(right + "…", "Helvetica", 8) > max_right:
            right = right[:-1]
        right = right.rstrip() + "…"
    canvas.drawRightString(w - 20 * mm, h - 12 * mm, right)
    if data.get("is_sample_data"):
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawCentredString(w / 2, h - 12 * mm, "SAMPLE / DEMO")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    bits = [data.get("report_date", ""), f"Page {doc.page}"]
    if data.get("is_sample_data"):
        bits.insert(0, "SAMPLE / DEMO")
    bits.append("Unaudited - not statutory accounts")
    canvas.drawCentredString(w / 2, 9 * mm, "  |  ".join(str(b) for b in bits if b))
    canvas.restoreState()


def _kpi_cards(rows: list[tuple], cols: int = 2) -> Table:
    cell_w = 8.5 * cm
    table_data = []
    row_buf: list = []
    for label, value, colour in rows:
        cell = Table(
            [[Paragraph(f"<b>{value}</b>", ParagraphStyle("v", fontSize=14, leading=18, textColor=colour))],
             [Paragraph(label, ParagraphStyle("l", fontSize=8, leading=11, textColor=MUTED))]],
            colWidths=[cell_w],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ]))
        row_buf.append(cell)
        if len(row_buf) == cols:
            table_data.append(row_buf)
            row_buf = []
    if row_buf:
        while len(row_buf) < cols:
            row_buf.append("")
        table_data.append(row_buf)
    t = Table(table_data, hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _cover_identity_lines(data: dict) -> list[str]:
    """Deduped cover lines so farm name, address and county do not stack twice."""
    p = data.get("profile") or {}
    pos = data.get("farm_position") or {}
    meeting = data.get("meeting") or {}
    farm_name = (data.get("farm_name") or "").strip()
    legal_name = (pos.get("legal_name") or "").strip()
    address = (pos.get("address") or "").strip()
    county = (pos.get("county") or p.get("county") or p.get("location") or "").strip()
    owner = (pos.get("owner_name") or p.get("owner_name") or "").strip()
    ha = pos.get("total_hectares") if pos.get("total_hectares") is not None else p.get("total_hectares")
    herd = pos.get("herd_number") or p.get("herd_number")

    lines: list[str] = []
    heading = legal_name or farm_name
    if heading:
        lines.append(heading)
    if farm_name and legal_name and farm_name.lower() not in legal_name.lower():
        lines.append(farm_name)
    if address:
        lines.append(address)
    if county and county.lower() not in address.lower():
        lines.append(county)
    if pos.get("vat_number"):
        lines.append(f"VAT {pos['vat_number']}")
    if owner and owner.lower() not in heading.lower():
        lines.append(owner)
    if herd:
        lines.append(f"Herd no. {herd}")
    if pos.get("processor"):
        lines.append(f"Processor: {pos['processor']}")
    if ha is not None:
        lines.append(f"{ha} hectares")
    if meeting.get("enterprises"):
        lines.append(str(meeting["enterprises"]))
    if meeting.get("period_label"):
        lines.append(str(meeting["period_label"]))
    return lines


def _page_cover(data: dict, st: dict) -> list:
    story = [Spacer(1, 1.4 * cm)]
    story.append(Paragraph("Farm Financial Report", st["cover_title"]))
    story.append(Paragraph(data["report_type_label"], st["cover_sub"]))
    if data.get("is_sample_data"):
        story.append(Paragraph("SAMPLE / DEMO DATA", st["cover_sample"]))
    story.append(Spacer(1, 0.8 * cm))
    if data.get("report_type") == "accountant":
        identity = _cover_identity_lines(data)
        if identity:
            story.append(Paragraph(identity[0], st["cover_farm"]))
            for line in identity[1:]:
                story.append(Paragraph(line, st["center"]))
        story.append(Spacer(1, 0.55 * cm))
        story.append(Paragraph(
            "Unaudited management information - not statutory accounts.",
            st["center"],
        ))
    else:
        story.append(Paragraph(data.get("farm_name") or "", st["cover_farm"]))
    story.append(Spacer(1, 0.7 * cm))
    story.append(Paragraph(data["report_date"], st["cover_sub"]))
    story.append(PageBreak())
    return story


def _page_executive(data: dict, st: dict) -> list:
    k = data["kpis"]
    h = data["health_score"]
    lowest = data.get("lowest_cash") or {}
    cards = _kpi_cards([
        ("Cash now", format_currency(k.get("cash_now", k.get("cash_available"))), NAVY),
        ("Lowest expected cash", format_currency(lowest.get("value", k.get("cash_available"))), NAVY),
        ("Expected Annual Profit", format_currency(k['annual_profit']), GREEN),
        ("Risk Level", k["risk_level"], _risk_light(k["risk_level"])),
    ])
    return [
        Paragraph("Executive Summary", st["title"]),
        cards,
        Spacer(1, 0.4 * cm),
        Paragraph(data["executive_summary"], st["body"]),
        PageBreak(),
    ]


def _page_meeting(data: dict, st: dict) -> list:
    meeting = data.get("meeting") or {}
    cards = _kpi_cards([
        ("Cash in the model", format_currency(meeting.get("cash_now", 0)), NAVY),
        ("Estimated outstanding debt", format_currency(meeting.get("total_debt", 0)), NAVY),
        ("Annual repayments", format_currency(meeting.get("annual_repayments", 0)), NAVY),
        (
            "Lowest expected cash (Forecast)",
            format_currency(meeting.get("lowest_cash", 0)),
            RED if float(meeting.get("lowest_cash") or 0) < 0 else GREEN,
        ),
    ])
    net_colour = GREEN if float(meeting.get("actual_net") or 0) >= 0 else RED
    actuals = _kpi_cards([
        ("Income — last 12 months (Actual)", format_currency(meeting.get("actual_income", 0)), GREEN),
        ("Costs — last 12 months (Actual)", format_currency(meeting.get("actual_costs", 0)), NAVY),
        ("Net — last 12 months (Actual)", format_currency(meeting.get("actual_net", 0)), net_colour),
        ("Lowest cash month (Forecast)", meeting.get("lowest_cash_month_label") or "—", AMBER),
    ])
    story = [
        Paragraph("Meeting summary", st["title"]),
        Paragraph(
            "Cash in the model is the opening figure in FarmBiddy as of this report date — not a live bank balance. "
            "Actual means recorded. Forecast is a seasonal look-ahead, not a bank statement.",
            st["muted"],
        ),
        Spacer(1, 0.2 * cm),
        Paragraph(meeting.get("period_label") or data.get("period_label") or "", st["body"]),
        Spacer(1, 0.3 * cm),
        cards,
        Spacer(1, 0.35 * cm),
        actuals,
        Spacer(1, 0.35 * cm),
        Paragraph(meeting.get("repayment_note") or "", st["body"]),
        Spacer(1, 0.3 * cm),
        Paragraph(data.get("executive_summary") or "", st["body"]),
        PageBreak(),
    ]
    return story


def _info_table(rows: list[tuple[str, str]], st: dict) -> Table:
    table = Table(
        [[Paragraph(f"<b>{a}</b>", st["body"]), Paragraph(str(b), st["body"])] for a, b in rows],
        colWidths=[5.5 * cm, 10.5 * cm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _page_farm_position(data: dict, st: dict) -> list:
    pos = data.get("farm_position") or {}
    land = pos.get("land_by_sector") or {}
    stock = pos.get("stock") or {}
    household = pos.get("household") or {}
    schemes = pos.get("schemes") or {}
    scheme_months = schemes.get("scheme_payment_months") or {}
    story = [
        Paragraph("Farm position", st["title"]),
        Paragraph(
            "Sample-farm records from Knockrow, not a balance sheet and not a live bank or lender statement.",
            st["muted"],
        ),
        Spacer(1, 0.25 * cm),
    ]
    cards = _kpi_cards([
        ("Cash in the model", format_currency(pos.get("cash", 0)), NAVY),
        ("Debtors", format_currency(pos.get("debtors", 0)), GREEN),
        ("Creditors", format_currency(pos.get("creditors", 0)), NAVY),
        ("Working capital", format_currency(pos.get("working_capital", 0)), GREEN),
    ])
    story += [cards, Spacer(1, 0.3 * cm)]
    story.append(Paragraph(
        "Working capital here is cash in the model + debtors − creditors. Cash is the opening figure in FarmBiddy as of the report date.",
        st["muted"],
    ))
    story.append(Spacer(1, 0.25 * cm))

    land_bits = []
    if land.get("dairy") is not None:
        land_bits.append(f"Dairy {land['dairy']} ha")
    if land.get("beef") is not None:
        land_bits.append(f"Beef {land['beef']} ha")
    if land.get("lamb") is not None:
        land_bits.append(f"Sheep {land['lamb']} ha")
    stock_bits = []
    if stock.get("milking_cows") is not None:
        stock_bits.append(f"{stock['milking_cows']} milking cows")
    if stock.get("cattle_on_farm") is not None:
        stock_bits.append(f"{stock['cattle_on_farm']} cattle")
    if stock.get("ewes") is not None:
        stock_bits.append(f"{stock['ewes']} ewes")
    tax_months = household.get("tax_payment_months") or []
    tax_when = ", ".join(_calendar_month_label(m) for m in tax_months) if tax_months else "—"
    story.append(Paragraph("Land, stock, household", st["h3"]))
    story.append(_info_table([
        ("Land", f"{pos.get('total_hectares') or '—'} ha" + (f" ({' · '.join(land_bits)})" if land_bits else "")),
        ("Stock on hand", ", ".join(stock_bits) if stock_bits else "—"),
        ("Drawings", f"{format_currency(household.get('drawings_monthly') or 0)} / month"),
        ("Off-farm income", f"{format_currency(household.get('off_farm_income_monthly') or 0)} / month"),
        ("Tax", f"{format_currency(household.get('tax_annual') or 0)} / year, paid {tax_when}"),
    ], st))
    story.append(Spacer(1, 0.3 * cm))

    suppliers = pos.get("supplier_credit") or []
    if suppliers:
        story.append(Paragraph("Supplier credit", st["h3"]))
        rows = [["Supplier", "Balance", "Terms"]]
        for row in suppliers:
            terms = row.get("terms_days")
            rows.append([
                row.get("supplier") or "—",
                format_currency(row.get("balance") or 0),
                f"{terms} days" if terms is not None else "—",
            ])
        table = Table(rows, colWidths=[7 * cm, 4.5 * cm, 4.5 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [table, Spacer(1, 0.3 * cm)]

    story.append(Paragraph("Schemes", st["h3"]))
    story.append(_info_table([
        ("BISS", f"{format_currency(schemes.get('biss') or 0)} in {_calendar_month_label(scheme_months.get('biss'))}"),
        ("ACRES", f"{format_currency(schemes.get('acres') or 0)} in {_calendar_month_label(scheme_months.get('acres'))}"),
        ("Other grants", f"{format_currency(schemes.get('other_grants') or 0)} in {_calendar_month_label(scheme_months.get('other_grants'))}"),
    ], st))
    if pos.get("notes"):
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph(pos["notes"], st["muted"]))
    story.append(PageBreak())
    return story


def _page_farm(data: dict, st: dict) -> list:
    p = data["profile"]
    f = data["farm"]
    litres = f.get("litres_per_cow", 0)
    total_litres = int(f.get("milking_cows", 0) * litres)
    rows = [
        ("Farm Name", data["farm_name"]),
        ("Milking Cows", str(f.get("milking_cows", "—"))),
        ("Milk Yield", f"{litres:,.0f} L/cow/year ({total_litres:,} L total)"),
        ("Milk Processor", p.get("milk_processor", "—")),
        ("Milk Price", f"{format_currency(f.get('milk_price', 0), decimals=2)} / L"),
        ("Employees", "Estimate from labour budget" if f.get("labour") else "—"),
        ("Land Area", p.get("location", "See farm records")),
        ("Operating Costs", f"{format_currency(data['forecast_summary'].get('annual_costs', 0))} / year"),
    ]
    table = Table([[Paragraph(f"<b>{a}</b>", st["body"]), Paragraph(str(b), st["body"])] for a, b in rows], colWidths=[5 * cm, 11 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [Paragraph("My Farm", st["title"]), Spacer(1, 0.3 * cm), table, PageBreak()]


def _page_snapshot(data: dict, st: dict) -> list:
    k = data["kpis"]
    def card(label, val, pct=None):
        c = GREEN if (pct is None or pct < 35) else AMBER if pct < 45 else RED
        return (label, val, c)
    cards = _kpi_cards([
        card("Revenue", format_currency(k['revenue'])),
        card("Operating Costs", format_currency(k['operating_costs'])),
        card("Net Profit", format_currency(k['net_profit'])),
        card("Cash Available", format_currency(k['cash_available'])),
        card("Debt (annual)", format_currency(k['debt'])),
        card("Feed Cost %", format_percent(k['feed_pct']), k["feed_pct"]),
        card("Labour Cost %", format_percent(k['labour_pct']), k["labour_pct"]),
        card("Vet Cost %", format_percent(k['vet_pct']), k["vet_pct"]),
        card("Electricity %", format_percent(k['electricity_pct']), k["electricity_pct"] or 0),
        card("Fuel Cost %", format_percent(k['fuel_pct']), k["fuel_pct"] or 0),
    ], cols=2)
    return [Paragraph("Financial Snapshot", st["title"]), cards, PageBreak()]


def _page_profitability(data: dict, st: dict, charts: dict) -> list:
    margin = data["forecast_summary"].get("profit_margin", 0)
    story = [Paragraph("Profitability Analysis", st["title"])]
    if charts.get("revenue_costs"):
        story += [Image(charts["revenue_costs"], width=16 * cm, height=7 * cm), Spacer(1, 0.3 * cm)]
    if charts.get("cost_breakdown"):
        story += [Image(charts["cost_breakdown"], width=14 * cm, height=6 * cm), Spacer(1, 0.3 * cm)]
    story.append(Paragraph(
        f"Revenue and costs track across the year with a profit margin of {format_percent(margin)}. "
        "When the cost line approaches revenue, margin tightens — feed and labour typically "
        "drive the largest movements.",
        st["body"],
    ))
    story.append(PageBreak())
    return story


def _page_cashflow(data: dict, st: dict, charts: dict) -> list:
    monthly = data.get("monthly_forecast") or []
    weak = [str(m.get("month")) for m in monthly if m.get("cashflow", 0) < 1500]
    weak_text = f"Weaker liquidity months: {', '.join(weak)}." if weak else "No severe liquidity dips flagged."
    story = [Paragraph("Cashflow Analysis", st["title"])]
    if charts.get("cashflow"):
        story.append(Image(charts["cashflow"], width=16 * cm, height=7 * cm))
    story.append(Spacer(1, 0.3 * cm))
    if charts.get("reserve"):
        story.append(Image(charts["reserve"], width=16 * cm, height=7 * cm))
    story += [
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Monthly cashflow shows how income and bills align through the season. {weak_text} "
            "Building reserves in strong months helps cover winter and tax payments.",
            st["body"],
        ),
        PageBreak(),
    ]
    return story


def _page_forecast(data: dict, st: dict, charts: dict) -> list:
    fs = data.get("forecast_scenarios", [])
    story = [Paragraph("12 Month Forecast", st["title"])]
    if charts.get("forecast_cases"):
        story.append(Image(charts["forecast_cases"], width=14 * cm, height=6 * cm))
    story.append(Spacer(1, 0.3 * cm))
    for s in fs:
        story.append(Paragraph(
            f"<b>{s.get('name')}</b>: Revenue {format_currency(s.get('revenue', 0))}, Profit {format_currency(s.get('profit', 0))}",
            st["body"],
        ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Best, expected, and worst cases reflect ±10% milk price sensitivity while holding "
        "costs steady. Use these cases to stress-test plans before major decisions.",
        st["body"],
    ))
    story.append(PageBreak())
    return story


def _page_monte(data: dict, st: dict, charts: dict) -> list:
    m = data.get("monte_carlo") or {}
    story = [Paragraph("Monte Carlo Simulation", st["title"])]
    if charts.get("monte") and m.get("iterations"):
        story.append(Image(charts["monte"], width=14 * cm, height=6 * cm))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            f"Confidence interval: {format_currency(m.get('confidence_low', 0))} to {format_currency(m.get('confidence_high', 0))}. "
            f"Probability of profit: {format_percent(m.get('probability_of_profit', 0) * 100, decimals=0)}. "
            f"Probability of loss: {format_percent(m.get('probability_of_loss', 0) * 100, decimals=0)}. "
            f"Probability of cash shortage: {format_percent(m.get('probability_of_cash_shortage', 0) * 100, decimals=0)}.",
            st["body"],
        ))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(m.get("summary", m.get("interpretation", "")), st["body"]))
    else:
        story.append(Paragraph("Monte Carlo simulation has not yet been run.", st["body"]))
    story.append(PageBreak())
    return story


def _page_scenarios(data: dict, st: dict, charts: dict) -> list:
    rows = [["Scenario", "Revenue", "Profit", "Cash Flow", "Risk"]]
    for s in data.get("scenarios", []):
        rows.append([
            s["scenario"],
            format_currency(s['revenue']),
            format_currency(s['profit']),
            format_currency(s['cashflow']),
            s["risk_level"],
        ])
    table = Table(rows, colWidths=[4.5 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [Paragraph("Scenario Analysis", st["title"]), table, Spacer(1, 0.4 * cm)]
    if charts.get("scenarios"):
        story.append(Image(charts["scenarios"], width=16 * cm, height=7 * cm))
    story.append(PageBreak())
    return story


def _page_intelligence(data: dict, st: dict) -> list:
    intel = data.get("financial_intelligence") or {}
    h = intel.get("health_score") or data["health_score"]
    strengths = intel.get("key_strengths") or ["Stable operational base"]
    weaknesses = intel.get("key_weaknesses") or ["No major weaknesses flagged"]
    opps = intel.get("opportunities") or []
    risks = intel.get("biggest_risks") or []
    return [
        Paragraph("Financial Intelligence", st["title"]),
        Paragraph(f"<b>Farm Health Score:</b> {h.get('score', '—')}/100 ({h.get('label', '')})", st["body"]),
        Spacer(1, 0.2 * cm),
        Paragraph(f"<b>Biggest Strength:</b> {strengths[0]}", st["body"]),
        Paragraph(f"<b>Biggest Weakness:</b> {weaknesses[0] if weaknesses else 'None flagged'}", st["body"]),
        Paragraph(f"<b>Biggest Opportunity:</b> {opps[0] if opps else 'Maintain current performance'}", st["body"]),
        Paragraph(
            f"<b>Greatest Financial Risk:</b> "
            f"{risks[0].get('driver', 'Market volatility') if risks else 'Monitor milk price and feed costs'} — "
            f"{risks[0].get('commentary', '') if risks else ''}",
            st["body"],
        ),
        Spacer(1, 0.3 * cm),
        Paragraph("<b>AI Summary</b>", st["h3"]),
        Paragraph(intel.get("plain_summary", data["executive_summary"]), st["body"]),
        PageBreak(),
    ]


def _page_actions(data: dict, st: dict) -> list:
    story = [Paragraph("Top Recommended Actions", st["title"])]
    for i, a in enumerate(data.get("recommended_actions", [])[:5], 1):
        story += [
            Paragraph(f"<b>{i}. Priority: {a.get('priority', 'Medium')}</b>", st["h3"]),
            Paragraph(f"<b>Recommendation:</b> {a.get('recommendation', '')}", st["body"]),
            Paragraph(f"<b>Estimated Benefit:</b> {a.get('estimated_benefit', '')}", st["body"]),
            Paragraph(f"<b>Reason:</b> {a.get('reason', '')}", st["body"]),
            Paragraph(f"<b>Expected Benefit:</b> {a.get('expected_benefit', '')}", st["muted"]),
            Spacer(1, 0.2 * cm),
        ]
    story.append(PageBreak())
    return story


def _status_color_name(status: str) -> str:
    v = (status or "").lower()
    if v in ("good", "low", "strong", "healthy", "positive"):
        return "#2d9f5f"
    if v in ("fair", "medium", "moderate", "tight", "watch"):
        return "#f59e0b"
    return "#dc2626"


def _page_risk_dashboard(data: dict, st: dict) -> list:
    story = [Paragraph("Risk Dashboard", st["title"])]
    for row in data.get("risk_dashboard", []):
        hex_color = _status_color_name(row["status"])
        story.append(Paragraph(
            f"<font color='{hex_color}'><b>{row['name']}: {row['status']}</b></font> — {row['explanation']}",
            st["body"],
        ))
        story.append(Spacer(1, 0.15 * cm))
    story.append(PageBreak())
    return story


def _page_advisor(data: dict, st: dict) -> list:
    text = data.get("advisor_summary", "").replace("\n", "<br/>")
    return [
        Paragraph("AI Farm Advisor Summary", st["title"]),
        Paragraph(text, st["body"]),
        PageBreak(),
    ]


def _page_action_plan(data: dict, st: dict) -> list:
    plan = data.get("action_plan", {})
    story = [Paragraph("Next 90 Day Action Plan", st["title"])]
    for heading, key in [("This Month", "this_month"), ("Next Month", "next_month"), ("Within 90 Days", "within_90_days")]:
        story.append(Paragraph(heading, st["h3"]))
        for item in plan.get(key, []):
            story.append(Paragraph(f"• {item}", st["body"]))
        story.append(Spacer(1, 0.2 * cm))
    story.append(PageBreak())
    return story


def _page_investment(data: dict, st: dict) -> list:
    inv = data.get("investment_readiness", {})
    comps = inv.get("components", {})
    rows = [[Paragraph("<b>Factor</b>", ParagraphStyle("h", fontSize=9, textColor=WHITE)),
             Paragraph("<b>Score</b>", ParagraphStyle("h2", fontSize=9, textColor=WHITE, alignment=TA_CENTER))]]
    for name, score in comps.items():
        rows.append([name.replace("_", " ").title(), str(score)])
    table = Table(rows, colWidths=[10 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [
        Paragraph("Investment Readiness", st["title"]),
        Paragraph(f"<b>Overall Investment Score: {inv.get('overall_score', '—')} / 100</b>", st["h2"]),
        Spacer(1, 0.2 * cm),
        table,
        Spacer(1, 0.3 * cm),
        Paragraph(inv.get("explanation", ""), st["body"]),
        PageBreak(),
    ]


def _category_totals_table(rows: list[dict], header: str) -> Table:
    table_rows = [[Paragraph(f"<b>{header}</b>", ParagraphStyle("h", fontSize=9, textColor=WHITE)),
                   Paragraph("<b>Actual</b>", ParagraphStyle("h2", fontSize=9, textColor=WHITE, alignment=TA_CENTER))]]
    for row in rows:
        table_rows.append([row.get("label", row.get("category_id", "")), format_currency(row.get("total", 0))])
    table = Table(table_rows, colWidths=[10 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _page_income_expenses_actual(data: dict, st: dict) -> list:
    """Actual recorded income/expenses (dataset + the farmer's own manual
    entries) - the real accounting figures, distinct from any forecast or
    scenario elsewhere in this report."""
    ie = data.get("income_expense_actual") or {}
    story = [
        Paragraph("Income & Expenses — Actual", st["title"]),
        Paragraph(
            _period_caption(ie.get("period")) + ". Recorded income and expenses, combining the farm's "
            "records with any transactions the farmer has logged directly in FarmBiddy.",
            st["muted"],
        ),
        Spacer(1, 0.3 * cm),
    ]
    cards = _kpi_cards([
        ("Total Income", format_currency(ie.get("income_total", 0)), GREEN),
        ("Total Expenses", format_currency(ie.get("expense_total", 0)), NAVY),
        ("Net Difference", format_currency(ie.get("difference", 0)),
         GREEN if ie.get("difference", 0) >= 0 else RED),
    ])
    story += [cards, Spacer(1, 0.4 * cm)]
    if ie.get("income_categories"):
        story += [Paragraph("Income by Category", st["h3"]), _category_totals_table(ie["income_categories"], "Category"), Spacer(1, 0.4 * cm)]
    if ie.get("expense_categories"):
        story += [Paragraph("Expenses by Category", st["h3"]), _category_totals_table(ie["expense_categories"], "Category"), Spacer(1, 0.3 * cm)]
    if ie.get("manual_income_total") or ie.get("manual_expense_total"):
        story.append(Paragraph(
            f"Of the above, {format_currency(ie.get('manual_income_total', 0))} income and "
            f"{format_currency(ie.get('manual_expense_total', 0))} expenses were entered directly "
            "by the farmer (not part of the underlying farm dataset).",
            st["muted"],
        ))
    story.append(PageBreak())
    return story


def _page_budget_variance(data: dict, st: dict) -> list:
    """Category-level Budget vs Actual - only for categories the farmer has
    actually set a budget for; unbudgeted categories are listed separately
    rather than shown with a fabricated zero variance."""
    bv = data.get("budget_variance") or {}
    story = [
        Paragraph("Budget vs Actual — By Category", st["title"]),
        Paragraph(bv.get("overall_summary", "No category budgets have been set yet."), st["body"]),
        Paragraph(_period_caption(bv.get("period") or data.get("period_label")), st["muted"]),
        Spacer(1, 0.3 * cm),
    ]
    categories = bv.get("categories") or []
    if categories:
        rows = [["Category", "Budget", "Actual", "Difference", "Status"]]
        for row in categories:
            rows.append([
                row["label"],
                format_currency(row["budget_total"]),
                format_currency(row["actual_total"]),
                format_currency(row["difference"]),
                row["status"].replace("_", " ").title(),
            ])
        table = Table(rows, colWidths=[4.5 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2.7 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [table, Spacer(1, 0.4 * cm)]
    unbudgeted = bv.get("unbudgeted_categories") or []
    if unbudgeted:
        labels = ", ".join(row["label"] for row in unbudgeted)
        story.append(Paragraph(f"<b>No budget set yet for:</b> {labels}.", st["muted"]))
    story.append(PageBreak())
    return story


def _page_loans_finance(data: dict, st: dict) -> list:
    """Summary-first presentation of the farm's debt register - the same
    figures the Loans & Finance page in the app already shows."""
    loans = data.get("loans_summary") or {}
    next_loan = loans.get("next_loan_to_clear")
    story = [Paragraph("Loans & Finance", st["title"])]
    story.append(Paragraph(
        "Outstanding is estimated from rate and remaining term, not a lender statement. Principal is the original amount on the farm record.",
        st["muted"],
    ))
    cards = _kpi_cards([
        ("Estimated outstanding", format_currency(loans.get("total_outstanding_debt", 0)), NAVY),
        ("Annual Repayments", format_currency(loans.get("total_annual_repayments", 0)), NAVY),
        ("Next Loan to Clear", next_loan.get("lender", "—") if next_loan else "None outstanding", GREEN),
    ])
    story += [cards, Spacer(1, 0.4 * cm)]
    clash = loans.get("low_cash_interaction")
    if clash:
        story.append(Paragraph(
            f"<b>Cash warning:</b> {clash.get('what') or clash.get('message') or 'Loan repayments land in an already low-cash month.'}",
            st["body"],
        ))
        story.append(Spacer(1, 0.25 * cm))
    register = loans.get("loans") or []
    if register:
        rows = [["Lender", "Principal", "Est. outstanding", "Rate", "Monthly", "Maturity"]]
        for loan in register:
            rate = loan.get("rate")
            rate_text = f"{rate:.2f}%" if isinstance(rate, (int, float)) else "—"
            rows.append([
                loan.get("lender", "—"),
                format_currency(loan.get("principal", 0)),
                format_currency(loan.get("outstanding_balance", 0)),
                rate_text,
                format_currency(loan.get("monthly_repayment", 0)),
                str(loan.get("maturity") or "—"),
            ])
        table = Table(rows, colWidths=[3.4 * cm, 2.6 * cm, 3.0 * cm, 2.0 * cm, 2.4 * cm, 2.2 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No loans on record for this farm.", st["body"]))
    story.append(PageBreak())
    return story


def _page_year_over_year(data: dict, st: dict) -> list:
    """Year-over-year comparison of Income, Costs, Farm Profit, and Cash
    Generated - restricted to like-for-like months whenever a year is
    partial, exactly as the app's Previous Performance page does."""
    yoy = data.get("year_over_year") or {}
    story = [Paragraph("Previous Performance — Year on Year", st["title"])]
    story.append(Paragraph(
        "Like-for-like months only when a year is partial. Farm profit is income minus costs, not a forecast.",
        st["muted"],
    ))
    years = yoy.get("years") or []
    if years:
        rows = [["Year", "Income", "Costs", "Farm Profit", "Cash Generated", "Coverage"]]
        for year_row in years:
            coverage = f"{year_row['months_covered']} of 12 months" if year_row.get("is_partial") else "Full year"
            rows.append([
                str(year_row["year"]),
                format_currency(year_row["income"]),
                format_currency(year_row["costs"]),
                format_currency(year_row["farm_profit"]),
                format_currency(year_row["cash_generated"]),
                coverage,
            ])
        table = Table(rows, colWidths=[1.8 * cm, 2.9 * cm, 2.9 * cm, 2.9 * cm, 2.9 * cm, 2.6 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [table, Spacer(1, 0.4 * cm)]
    else:
        story.append(Paragraph("Not enough recorded history yet to compare years.", st["body"]))
    for comparison in yoy.get("comparisons") or []:
        note = comparison.get("note")
        story.append(Paragraph(
            f"<b>{comparison['year']} vs {comparison['previous_year']}</b>"
            + (f" — {note}" if note else ""),
            st["h3"],
        ))
        for metric_key, metric_label in (
            ("income", "Income"), ("costs", "Costs"),
            ("farm_profit", "Farm Profit"), ("cash_generated", "Cash Generated"),
        ):
            metric = comparison.get(metric_key)
            if not metric:
                continue
            change_pct = f" ({metric['change_pct']:+.1f}%)" if metric.get("change_pct") is not None else ""
            story.append(Paragraph(
                f"{metric_label}: {format_currency(metric['current'])} vs {format_currency(metric['previous'])} "
                f"({format_currency(metric['change'])}{change_pct})",
                st["body"],
            ))
        story.append(Spacer(1, 0.2 * cm))
    story.append(PageBreak())
    return story


def _page_closing(data: dict, st: dict) -> list:
    lines = [
        Spacer(1, 4.5 * cm),
        Paragraph("FarmBiddy", st["cover_sub"]),
        Spacer(1, 0.4 * cm),
        Paragraph(
            "Automatically generated. Unaudited management information - not statutory accounts.",
            st["center"],
        ),
    ]
    if data.get("is_sample_data"):
        lines.append(Paragraph("SAMPLE / DEMO DATA", st["cover_sample"]))
    lines += [
        Spacer(1, 1 * cm),
        Paragraph(data["report_date"], st["center"]),
        Paragraph(f"Software Version {data.get('software_version', SOFTWARE_VERSION)}", st["muted"]),
    ]
    return lines


def _page_cash_forecast(data: dict, st: dict, charts: dict) -> list:
    monthly = data.get("monthly_forecast") or []
    lowest = data.get("lowest_cash") or {}
    story = [
        Paragraph("Expected cash — Forecast", st["title"]),
        Paragraph(
            "Seasonal 12-month forecast starting from cash in the model. Month names are calendar months "
            "(January pattern first, BISS in October). This is not a dated bank statement.",
            st["muted"],
        ),
        Spacer(1, 0.25 * cm),
        Paragraph(
            f"Lowest expected cash: <b>{format_currency(lowest.get('value', 0))}</b> "
            f"({lowest.get('month_label') or '—'}).",
            st["body"],
        ),
        Spacer(1, 0.3 * cm),
    ]
    if charts.get("reserve"):
        story += [Image(charts["reserve"], width=16 * cm, height=7 * cm), Spacer(1, 0.3 * cm)]
    if charts.get("cashflow"):
        story += [Image(charts["cashflow"], width=16 * cm, height=7 * cm), Spacer(1, 0.3 * cm)]
    if monthly:
        rows = [["Month", "Cash movement", "Running cash"]]
        for month in monthly:
            mark = " ← lowest" if month.get("month") == lowest.get("month") else ""
            rows.append([
                f"{_calendar_month_label(month.get('month'))}{mark}",
                format_currency(month.get("combined_cashflow", month.get("cashflow", 0))),
                format_currency(_month_cash(month)),
            ])
        table = Table(rows, colWidths=[4 * cm, 6 * cm, 6 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
    story.append(PageBreak())
    return story


def _page_milk_down(data: dict, st: dict) -> list:
    comparison = (data.get("milk_down") or {}).get("comparison") or {}
    story = [
        Paragraph("If milk falls 5c/L", st["title"]),
        Paragraph(
            "Same What If? engine as the app. Nothing here is saved as a real farm figure. "
            "Beef and sheep are not directly changed by a milk-price move; whole-farm cash still is.",
            st["muted"],
        ),
        Spacer(1, 0.3 * cm),
    ]
    if not comparison:
        story.append(Paragraph("This comparison could not be calculated for this farm.", st["body"]))
        story.append(PageBreak())
        return story
    cards = _kpi_cards([
        ("Income change", format_currency(comparison.get("revenue_difference", 0)), NAVY),
        ("Profit change", format_currency(comparison.get("profit_difference", 0)), NAVY),
        ("Lowest cash now", format_currency(comparison.get("min_cash_base", 0)), GREEN),
        ("Lowest cash if milk −5c", format_currency(comparison.get("min_cash_scenario", 0)), RED),
    ])
    story += [cards, Spacer(1, 0.4 * cm)]
    rows = [
        ["Figure", "Now", "Milk −5c/L", "Change"],
        ["Income", format_currency(comparison.get("revenue_base", 0)), format_currency(comparison.get("revenue_scenario", 0)), format_currency(comparison.get("revenue_difference", 0))],
        ["Farm profit", format_currency(comparison.get("profit_base", 0)), format_currency(comparison.get("profit_scenario", 0)), format_currency(comparison.get("profit_difference", 0))],
        ["Lowest cash", format_currency(comparison.get("min_cash_base", 0)), format_currency(comparison.get("min_cash_scenario", 0)), "—"],
        ["Year-end cash", format_currency(comparison.get("year_end_cash_base", 0)), format_currency(comparison.get("year_end_cash_scenario", 0)), "—"],
    ]
    table = Table(rows, colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(PageBreak())
    return story


def _page_sector_contribution(data: dict, st: dict) -> list:
    rows_data = data.get("sector_performance") or []
    story = [
        Paragraph("Contribution by enterprise", st["title"]),
        Paragraph(
            "How Dairy, Beef and Sheep contribute on recorded figures. "
            "Cash and bills are still whole-farm — shared costs are not a clean split.",
            st["muted"],
        ),
        Spacer(1, 0.3 * cm),
    ]
    if not rows_data:
        story.append(Paragraph("No enterprise breakdown is available for this farm.", st["body"]))
        story.append(PageBreak())
        return story
    rows = [["Enterprise", "Income", "Farm profit", "Margin"]]
    for row in rows_data:
        rows.append([
            row.get("label") or SECTOR_LABELS.get(row.get("sector"), row.get("sector", "—")),
            format_currency(row.get("revenue", 0)),
            format_currency(row.get("profit", 0)),
            format_percent(row.get("margin_pct", 0)),
        ])
    table = Table(rows, colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(PageBreak())
    return story


PAGE_BUILDERS = {
    "cover": lambda d, s, c: _page_cover(d, s),
    "executive": lambda d, s, c: _page_executive(d, s),
    "farm": lambda d, s, c: _page_farm(d, s),
    "snapshot": lambda d, s, c: _page_snapshot(d, s),
    "profitability": lambda d, s, c: _page_profitability(d, s, c),
    "cashflow": lambda d, s, c: _page_cashflow(d, s, c),
    "forecast": lambda d, s, c: _page_forecast(d, s, c),
    "monte_carlo": lambda d, s, c: _page_monte(d, s, c),
    "scenarios": lambda d, s, c: _page_scenarios(d, s, c),
    "intelligence": lambda d, s, c: _page_intelligence(d, s),
    "actions": lambda d, s, c: _page_actions(d, s),
    "risk_dashboard": lambda d, s, c: _page_risk_dashboard(d, s),
    "advisor": lambda d, s, c: _page_advisor(d, s),
    "action_plan": lambda d, s, c: _page_action_plan(d, s),
    "investment": lambda d, s, c: _page_investment(d, s),
    "income_expenses_actual": lambda d, s, c: _page_income_expenses_actual(d, s),
    "budget_variance": lambda d, s, c: _page_budget_variance(d, s),
    "loans_finance": lambda d, s, c: _page_loans_finance(d, s),
    "year_over_year": lambda d, s, c: _page_year_over_year(d, s),
    "meeting": lambda d, s, c: _page_meeting(d, s),
    "farm_position": lambda d, s, c: _page_farm_position(d, s),
    "cash_forecast": lambda d, s, c: _page_cash_forecast(d, s, c),
    "milk_down": lambda d, s, c: _page_milk_down(d, s),
    "sector_contribution": lambda d, s, c: _page_sector_contribution(d, s),
    "closing": lambda d, s, c: _page_closing(d, s),
}


def _build_pdf(data: dict, pages: list[str], charts: dict) -> str:
    ensure_output_dirs()
    safe_name = data["farm_name"].replace(" ", "_").lower()[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{data['report_type']}_{ts}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)

    doc = _ReportDoc(
        filepath,
        data,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=28 * mm,
        bottomMargin=20 * mm,
        title=f"FarmBiddy Report — {data['farm_name']}",
        author="FarmBiddy",
    )
    st = _styles()
    story: list = []
    for page_key in pages:
        builder = PAGE_BUILDERS.get(page_key)
        if builder:
            story.extend(builder(data, st, charts))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return filepath


def get_report_preview(
    farm_id: str | None = None,
    report_type: str = "full",
    report_date: str | None = None,
    sectors: list[str] | None = None,
) -> dict:
    """JSON preview for the Reports UI before download."""
    data = collect_report_data(farm_id, report_type, report_date, sectors=sectors)
    kpis = data.get("kpis") or {}
    return {
        "success": True,
        "farm_file": data["farm_file"],
        "farm_name": data["farm_name"],
        "report_type": report_type,
        "report_type_label": data["report_type_label"],
        "report_date": data["report_date"],
        "executive_summary": data["executive_summary"],
        "health_score": data["health_score"],
        "kpis": {
            "cash_now": kpis.get("cash_now"),
            "cash_available": kpis.get("cash_available"),
            "annual_profit": kpis.get("annual_profit"),
            "risk_level": kpis.get("risk_level"),
            "health_score": kpis.get("health_score"),
        },
        "preview_kpis": data.get("preview_kpis") or [],
        "page_count_estimate": len(PAGE_SETS.get(report_type, PAGE_SETS["full"])),
        "sections": PAGE_SETS.get(report_type, PAGE_SETS["full"]),
    }


def generate_farmer_report(
    farm_id: str | None = None,
    report_type: str = "full",
    report_date: str | None = None,
    sectors: list[str] | None = None,
) -> dict:
    """Generate PDF report and return download metadata."""
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Invalid report_type. Choose from: {', '.join(REPORT_TYPES)}")

    data = collect_report_data(farm_id, report_type, report_date, sectors=sectors)
    charts = _generate_report_charts(data)
    pages = PAGE_SETS.get(report_type, PAGE_SETS["full"])

    try:
        filepath = _build_pdf(data, pages, charts)
    finally:
        for path in charts.values():
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    filename = os.path.basename(filepath)
    return {
        "success": True,
        "farm_file": data["farm_file"],
        "farm_name": data["farm_name"],
        "report_type": report_type,
        "report_type_label": data["report_type_label"],
        "report_date": data["report_date"],
        "filename": filename,
        "download_url": f"/report-files/{filename}",
        "page_count": len(pages),
        "executive_summary": data["executive_summary"],
        "generated_at": data["generated_at"],
        "health_score": data.get("health_score") or {},
        "kpis": data.get("kpis") or {},
        "preview_kpis": data.get("preview_kpis") or [],
    }
