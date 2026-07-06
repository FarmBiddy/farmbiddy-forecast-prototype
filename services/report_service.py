"""
FarmBiddy Farmer Edition — professional PDF report generation.

Consumes existing dashboard, forecast, scenario, Monte Carlo, and intelligence
services without modifying the forecast engine.
"""

from __future__ import annotations

import os
import random
import tempfile
from datetime import datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
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

from config.paths import REPORTS_DIR, ensure_output_dirs
from forecast_engine.alerts import generate_alerts
from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.costs import calculate_costs
from forecast_engine.monte_carlo import run_monte_carlo
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.scenarios import calculate_scenarios
from models.api_models import ForecastOutputs, SandboxOutputs
from services.farmer_dashboard_service import get_farmer_profile, resolve_farm_file, resolve_sectors
from services.financial_intelligence_service import get_financial_intelligence
from services.forecast_service import run_forecast, run_sandbox_forecast
from services.multi_sector_farm import load_farm_for_analysis

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
}


def _safe_pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


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
            benefit = f"€{int(farm.get('feed', 0) * 0.05):,} annually"
        elif "debt" in title.lower() or "loan" in title.lower():
            benefit = f"€{int(farm.get('loan_repayments', 0) * 0.08):,} interest savings potential"
        elif "cash" in title.lower():
            benefit = f"€{int(max(forecast.get('annual_profit', 0) * 0.05, 5000)):,} buffer target"
        else:
            benefit = f"€{int(max(forecast.get('annual_profit', 0) * 0.03, 3000)):,} estimated impact"
        actions.append({
            "priority": priority,
            "recommendation": title,
            "estimated_benefit": benefit,
            "reason": reason or "Based on your latest farm forecast.",
            "expected_benefit": "Improved margin resilience and clearer cash planning.",
        })

    if len(actions) < 5:
        defaults = [
            ("Review feed supplier contracts before winter.", "Feed prices may rise seasonally.", f"€{int(farm.get('feed', 0) * 0.05):,} annually"),
            ("Update financial records monthly.", "Better records improve decision speed.", "Reduced admin cost and fewer surprises"),
            ("Run a new forecast after major changes.", "Keeps plans aligned with reality.", "Better timing for investments"),
            ("Review labour efficiency per cow.", "Labour is a major fixed cost.", f"€{int(farm.get('labour', 0) * 0.04):,} potential savings"),
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
        f"Annual profit is forecast at €{profit:,.0f} with a farm health score of "
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
            f"Profit margin is {margin:.1f}% on current assumptions."),
        row("Debt", "High" if loan_pct > 15 else "Moderate" if loan_pct > 10 else "Low",
            f"Loan repayments are {loan_pct:.1f}% of revenue."),
        row("Cashflow", "Negative" if monthly_cf < 0 else "Good" if monthly_cf >= 2000 else "Tight",
            f"Average monthly cashflow is €{monthly_cf:,.0f}."),
        row("Milk Price Exposure", forecast.get("risk_level", "Medium"),
            "Income is sensitive to milk price changes — test scenarios regularly."),
        row("Feed Dependency", health.get("feed_pressure", "Moderate"),
            f"Feed represents {feed_pct:.0f}% of revenue."),
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
    intel = get_financial_intelligence(farm_id, sectors=selected)

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

    opening = farm.get("opening_cash_balance", 0)
    end_cash = monthly[-1].get("running_balance", opening) if monthly else opening

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
    return {
        "farm_file": farm_file,
        "farm_name": profile.get("farm_name", farm.get("farm_name")),
        "report_type": report_type,
        "report_type_label": REPORT_TYPES.get(report_type, "Full Financial Report"),
        "report_date": generated,
        "generated_at": datetime.now().isoformat(),
        "software_version": SOFTWARE_VERSION,
        "profile": profile,
        "farm": farm,
        "forecast_summary": summary,
        "monthly_forecast": monthly,
        "kpis": {
            "cash_available": end_cash,
            "annual_profit": profit,
            "risk_level": risk,
            "health_score": health.get("score", 70),
            "revenue": revenue,
            "operating_costs": costs,
            "net_profit": profit,
            "debt": farm.get("loan_repayments", 0),
            "feed_pct": feed_pct,
            "labour_pct": _safe_pct(farm.get("labour", 0), revenue),
            "vet_pct": _safe_pct(farm.get("vet", 0), revenue),
            "electricity_pct": _safe_pct(farm.get("electricity", 0), revenue),
            "fuel_pct": _safe_pct(farm.get("fuel", 0), revenue),
        },
        "cost_breakdown": cost_breakdown,
        "health_score": health,
        "executive_summary": _executive_narrative(
            {**summary, "risk_level": risk}, health, intel
        ),
        "financial_intelligence": intel,
        "monte_carlo": monte,
        "monte_profits": profits,
        "scenarios": scenarios,
        "forecast_scenarios": forecast_scenarios,
        "recommended_actions": actions,
        "action_plan": action_plan,
        "advisor_summary": _advisor_page(intel, {**summary, "risk_level": risk}, health),
        "risk_dashboard": risk_rows,
        "investment_readiness": investment,
        "alerts": forecast_run.get("alerts", []),
    }


# ---------------------------------------------------------------------------
# Chart generation (matplotlib → temp PNG for ReportLab)
# ---------------------------------------------------------------------------

def _save_chart(fig, prefix: str) -> str:
    path = os.path.join(tempfile.gettempdir(), f"farmbiddy_{prefix}_{os.getpid()}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _chart_revenue_costs(monthly: list[dict]) -> str:
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
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [k for k, v in breakdown.items() if v]
    values = [v for v in breakdown.values() if v]
    colors_list = ["#2d9f5f", "#0f2744", "#64748b", "#f59e0b", "#1e3a5f", "#94a3b8", "#dc2626", "#4ade80", "#60a5fa"]
    ax.barh(labels, values, color=colors_list[: len(labels)])
    ax.set_title("Cost Breakdown", fontsize=14, fontweight="bold", color="#0f2744")
    fig.tight_layout()
    return _save_chart(fig, "costs")


def _chart_cashflow(monthly: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    months = [str(m.get("month", i)) for i, m in enumerate(monthly, 1)]
    cf = [m.get("cashflow", 0) for m in monthly]
    colors_bars = ["#2d9f5f" if v >= 0 else "#dc2626" for v in cf]
    ax.bar(months, cf, color=colors_bars)
    ax.axhline(0, color="#64748b", linewidth=0.8)
    ax.set_title("Monthly Cashflow", fontsize=14, fontweight="bold", color="#0f2744")
    fig.tight_layout()
    return _save_chart(fig, "cashflow")


def _chart_reserve(monthly: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    months = [str(m.get("month", i)) for i, m in enumerate(monthly, 1)]
    bal = [m.get("running_balance", 0) for m in monthly]
    ax.fill_between(range(len(months)), bal, alpha=0.3, color="#2d9f5f")
    ax.plot(months, bal, color="#0f2744", linewidth=2.5, marker="o")
    ax.set_title("Cash Reserve Trend", fontsize=14, fontweight="bold", color="#0f2744")
    fig.tight_layout()
    return _save_chart(fig, "reserve")


def _chart_forecast_cases(scenarios: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(7, 4))
    names = [s.get("name", "") for s in scenarios]
    profits = [s.get("profit", 0) for s in scenarios]
    ax.bar(names, profits, color=["#2d9f5f", "#0f2744", "#f59e0b"])
    ax.set_title("12-Month Forecast Cases", fontsize=14, fontweight="bold", color="#0f2744")
    plt.xticks(rotation=15, ha="right")
    fig.tight_layout()
    return _save_chart(fig, "forecast_cases")


def _chart_monte(profits: list[float]) -> str:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(profits, bins=30, color="#2d9f5f", edgecolor="white", alpha=0.85)
    ax.axvline(sum(profits) / len(profits), color="#0f2744", linestyle="--", label="Expected")
    ax.set_title("Monte Carlo Profit Distribution", fontsize=14, fontweight="bold", color="#0f2744")
    ax.legend()
    fig.tight_layout()
    return _save_chart(fig, "monte")


def _chart_scenarios(scenarios: list[dict]) -> str:
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
             "cashflow": (revenue - costs) / 12, "running_balance": data["kpis"]["cash_available"]}
            for i in range(1, 13)
        ]
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
        "title": ParagraphStyle("Title", parent=base["Heading1"], fontSize=22, textColor=NAVY, spaceAfter=12),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=16, textColor=NAVY, spaceBefore=8, spaceAfter=8),
        "h3": ParagraphStyle("H3", parent=base["Heading3"], fontSize=12, textColor=GREEN, spaceAfter=6),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#1a2332")),
        "muted": ParagraphStyle("Muted", parent=base["Normal"], fontSize=9, textColor=MUTED, leading=12),
        "center": ParagraphStyle("Center", parent=base["Normal"], fontSize=11, alignment=TA_CENTER, textColor=MUTED),
        "cover_title": ParagraphStyle("CoverTitle", parent=base["Heading1"], fontSize=28, textColor=NAVY, alignment=TA_CENTER, spaceAfter=16),
        "cover_sub": ParagraphStyle("CoverSub", parent=base["Normal"], fontSize=14, textColor=GREEN, alignment=TA_CENTER, spaceAfter=8),
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
    canvas.drawRightString(w - 20 * mm, h - 12 * mm, data.get("farm_name", "Farm Report"))
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w / 2, 10 * mm, f"FarmBiddy Farmer Edition  ·  {data.get('report_date', '')}  ·  Page {doc.page}")
    canvas.drawCentredString(w / 2, 6 * mm, "Confidential — For farm management purposes only")
    canvas.restoreState()


def _kpi_cards(rows: list[tuple], cols: int = 2) -> Table:
    cell_w = 8.5 * cm
    table_data = []
    row_buf: list = []
    for label, value, colour in rows:
        cell = Table(
            [[Paragraph(f"<b>{value}</b>", ParagraphStyle("v", fontSize=14, textColor=colour))],
             [Paragraph(label, ParagraphStyle("l", fontSize=8, textColor=MUTED))]],
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


def _page_cover(data: dict, st: dict) -> list:
    story = [Spacer(1, 4 * cm)]
    story.append(Paragraph("FarmBiddy Farmer Edition", st["cover_sub"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Farm Financial Report", st["cover_title"]))
    story.append(Paragraph(data["report_type_label"], st["cover_sub"]))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(f"<b>{data['farm_name']}</b>", ParagraphStyle("fn", fontSize=20, alignment=TA_CENTER, textColor=NAVY)))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(data["report_date"], st["center"]))
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("<b>Confidential</b>", ParagraphStyle("conf", fontSize=11, alignment=TA_CENTER, textColor=RED)))
    story.append(PageBreak())
    return story


def _page_executive(data: dict, st: dict) -> list:
    k = data["kpis"]
    h = data["health_score"]
    cards = _kpi_cards([
        ("Cash Available", f"€{k['cash_available']:,.0f}", NAVY),
        ("Expected Annual Profit", f"€{k['annual_profit']:,.0f}", GREEN),
        ("Risk Level", k["risk_level"], _risk_light(k["risk_level"])),
        ("Farm Health Score", f"{h.get('score', k['health_score'])}/100", GREEN),
    ])
    return [
        Paragraph("Executive Summary", st["title"]),
        cards,
        Spacer(1, 0.4 * cm),
        Paragraph(data["executive_summary"], st["body"]),
        PageBreak(),
    ]


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
        ("Milk Price", f"€{f.get('milk_price', 0):.2f} / L"),
        ("Employees", "Estimate from labour budget" if f.get("labour") else "—"),
        ("Land Area", p.get("location", "See farm records")),
        ("Operating Costs", f"€{data['forecast_summary'].get('annual_costs', 0):,.0f} / year"),
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
        card("Revenue", f"€{k['revenue']:,.0f}"),
        card("Operating Costs", f"€{k['operating_costs']:,.0f}"),
        card("Net Profit", f"€{k['net_profit']:,.0f}"),
        card("Cash Available", f"€{k['cash_available']:,.0f}"),
        card("Debt (annual)", f"€{k['debt']:,.0f}"),
        card("Feed Cost %", f"{k['feed_pct']:.1f}%", k["feed_pct"]),
        card("Labour Cost %", f"{k['labour_pct']:.1f}%", k["labour_pct"]),
        card("Vet Cost %", f"{k['vet_pct']:.1f}%", k["vet_pct"]),
        card("Electricity %", f"{k['electricity_pct']:.1f}%", k["electricity_pct"] or 0),
        card("Fuel Cost %", f"{k['fuel_pct']:.1f}%", k["fuel_pct"] or 0),
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
        f"Revenue and costs track across the year with a profit margin of {margin:.1f}%. "
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
            f"<b>{s.get('name')}</b>: Revenue €{s.get('revenue', 0):,.0f}, Profit €{s.get('profit', 0):,.0f}",
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
            f"Confidence interval: €{m.get('confidence_low', 0):,.0f} to €{m.get('confidence_high', 0):,.0f}. "
            f"Probability of profit: {m.get('probability_of_profit', 0) * 100:.0f}%. "
            f"Probability of loss: {m.get('probability_of_loss', 0) * 100:.0f}%. "
            f"Probability of cash shortage: {m.get('probability_of_cash_shortage', 0) * 100:.0f}%.",
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
            f"€{s['revenue']:,.0f}",
            f"€{s['profit']:,.0f}",
            f"€{s['cashflow']:,.0f}",
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


def _page_closing(data: dict, st: dict) -> list:
    return [
        Spacer(1, 5 * cm),
        Paragraph("FarmBiddy Farmer Edition", st["cover_sub"]),
        Spacer(1, 0.5 * cm),
        Paragraph("Helping Dairy Farmers Make Better Financial Decisions", st["center"]),
        Spacer(1, 1 * cm),
        Paragraph("Automatically Generated Report", st["center"]),
        Paragraph(data["report_date"], st["center"]),
        Paragraph(f"Software Version {data.get('software_version', SOFTWARE_VERSION)}", st["muted"]),
    ]


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
        bottomMargin=22 * mm,
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
            "cash_available": data["kpis"]["cash_available"],
            "annual_profit": data["kpis"]["annual_profit"],
            "risk_level": data["kpis"]["risk_level"],
            "health_score": data["kpis"]["health_score"],
        },
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
    }
