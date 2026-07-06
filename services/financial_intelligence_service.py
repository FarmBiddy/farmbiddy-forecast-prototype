"""
Financial Intelligence — farmer decision support for FarmBiddy Farmer Edition.

Uses existing forecast, advisory, risk, and alert engines when available.
Falls back to safe calculations from farm JSON so the page is never empty.
"""

from __future__ import annotations

from typing import Any

from forecast_engine.alerts import generate_alerts
from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from forecast_engine.risk_drivers import calculate_risk_drivers
from forecast_engine.risk_level import calculate_risk_level
from models.api_models import ForecastOutputs
from services.advisory_summary_service import generate_advisory_summary
from services.farmer_dashboard_service import get_farmer_profile, resolve_farm_file, resolve_sectors
from services.forecast_service import run_forecast
from services.multi_sector_farm import load_farm_for_analysis


def _build_forecast_from_farm(farm: dict) -> dict:
    """Minimal forecast result from farm JSON when full engine output is unavailable."""
    revenue = calculate_revenue(farm)
    costs = calculate_costs(farm)
    profit = calculate_profit(revenue, costs)
    margin = (profit / revenue * 100) if revenue > 0 else 0
    monthly_cf = calculate_monthly_cashflow(revenue, costs)
    feed_ratio = (farm.get("feed", 0) / revenue * 100) if revenue > 0 else 0
    herd = farm.get("milking_cows", 120) or 120
    alerts = generate_alerts(farm, profit, revenue, costs, monthly_cf)
    risk = calculate_risk_level(alerts, margin / 100 if revenue else 0)
    monthly = generate_monthly_forecast(
        farm, revenue, costs, farm.get("opening_cash_balance", 0)
    )
    return {
        "farm_name": farm.get("farm_name", "My Farm"),
        "annual_revenue": round(revenue, 2),
        "annual_costs": round(costs, 2),
        "annual_profit": round(profit, 2),
        "profit_margin": round(margin, 2),
        "feed_cost_ratio": round(feed_ratio, 2),
        "cost_ratio": round(costs / revenue * 100, 2) if revenue else 0,
        "revenue_per_cow": round(revenue / herd, 2) if herd else 0,
        "profit_per_cow": round(profit / herd, 2) if herd else 0,
        "monthly_cashflow": round(monthly_cf, 2),
        "risk_level": risk,
        "alerts": alerts,
        "monthly_forecast": monthly,
    }


def _load_forecast_context(
    farm_file: str,
    sectors: list[str] | None = None,
) -> tuple[dict, dict, dict]:
    """Return farm dict, full forecast result, and advisory summary."""
    selected = resolve_sectors(sectors, farm_file)
    farm = load_farm_for_analysis(farm_file, selected)
    try:
        outputs = ForecastOutputs(
            forecast_summary=True,
            monthly_forecast=True,
            alerts=True,
            risk_level=True,
            top_risk_drivers=True,
            advisory_summary=True,
            kpis=True,
        )
        api_result = run_forecast(
            farm_file=farm_file,
            outputs=outputs,
            save_result=False,
            generate_charts=False,
            sectors=selected,
        )
        summary = api_result.get("forecast_summary") or {}
        full = _build_forecast_from_farm(farm)
        full.update({
            "annual_revenue": summary.get("annual_revenue", full["annual_revenue"]),
            "annual_costs": summary.get("annual_costs", full["annual_costs"]),
            "annual_profit": summary.get("annual_profit", full["annual_profit"]),
            "profit_margin": summary.get("profit_margin", full["profit_margin"]),
            "risk_level": api_result.get("risk_level", full["risk_level"]),
            "alerts": api_result.get("alerts", full["alerts"]),
            "monthly_forecast": api_result.get("monthly_forecast", full["monthly_forecast"]),
        })
        if api_result.get("kpis"):
            full.update(api_result["kpis"])
        advisory = api_result.get("advisory_summary") or generate_advisory_summary(full, farm)
        risk_drivers = api_result.get("top_risk_drivers") or calculate_risk_drivers(farm, full)
        return farm, full, {"advisory": advisory, "risk_drivers": risk_drivers}
    except Exception:
        full = _build_forecast_from_farm(farm)
        advisory = generate_advisory_summary(full, farm)
        risk_drivers = calculate_risk_drivers(farm, full)
        return farm, full, {"advisory": advisory, "risk_drivers": risk_drivers}


def _health_score(forecast: dict, farm: dict) -> dict:
    score = 70
    margin = forecast.get("profit_margin", 0)
    risk = forecast.get("risk_level", "Medium")
    feed = forecast.get("feed_cost_ratio", 35)
    monthly_cf = forecast.get("monthly_cashflow", 0)
    opening = farm.get("opening_cash_balance", 0)
    loans = farm.get("loan_repayments", 0)
    revenue = forecast.get("annual_revenue", 1)

    if margin >= 20:
        score += 12
    elif margin >= 10:
        score += 5
    elif margin < 5:
        score -= 15

    if risk == "Low":
        score += 10
    elif risk == "High":
        score -= 20
    elif risk == "Medium":
        score -= 5

    if feed > 40:
        score -= 12
    elif feed > 35:
        score -= 6
    elif feed <= 30:
        score += 5

    if monthly_cf < 0:
        score -= 15
    elif monthly_cf > 3000:
        score += 5

    if opening < forecast.get("annual_costs", 0) / 12:
        score -= 8

    loan_pct = (loans / revenue * 100) if revenue else 0
    if loan_pct > 15:
        score -= 8

    score = max(0, min(100, score))
    label = "Excellent" if score >= 85 else "Good" if score >= 70 else "Fair" if score >= 50 else "Needs attention"

    return {
        "score": score,
        "label": label,
        "profitability": "Good" if margin >= 15 else "Fair" if margin >= 8 else "Weak",
        "cashflow": "Good" if monthly_cf >= 2000 else "Tight" if monthly_cf >= 0 else "Negative",
        "feed_pressure": "High" if feed > 35 else "Moderate" if feed > 30 else "Low",
        "debt_pressure": "High" if loan_pct > 15 else "Moderate" if loan_pct > 10 else "Low",
        "risk_level": risk,
    }


def _opportunities(forecast: dict, farm: dict) -> list[str]:
    items: list[str] = []
    if forecast.get("profit_margin", 0) >= 15 and forecast.get("annual_profit", 0) > 0:
        items.append("Consider using surplus cash to reduce debt or build reserves.")
    if forecast.get("risk_level") == "Low":
        items.append("Stable outlook — good time to plan improvements or modest expansion.")
    if forecast.get("feed_cost_ratio", 100) <= 32:
        items.append("Feed costs are well controlled — maintain current ration strategy.")
    if forecast.get("profit_per_cow", 0) > 800:
        items.append("Strong profit per cow — explore yield or quality bonuses with your processor.")
    if farm.get("litres_per_cow", 0) < 6000:
        items.append("Improving litres per cow by 0.5 L/day could lift annual income materially.")
    if not items:
        items.append("Focus on cost control and cash monitoring to create future opportunities.")
    return items[:5]


def _recommended_actions(forecast: dict, farm: dict, advisory: dict) -> list[dict]:
    actions: list[dict] = []
    feed = forecast.get("feed_cost_ratio", 0)
    margin = forecast.get("profit_margin", 0)
    monthly_cf = forecast.get("monthly_cashflow", 0)
    opening = farm.get("opening_cash_balance", 0)
    loans = farm.get("loan_repayments", 0)
    revenue = forecast.get("annual_revenue", 1)
    loan_pct = (loans / revenue * 100) if revenue else 0

    if feed > 35:
        actions.append({
            "title": "Review feed supplier contracts and ration efficiency.",
            "reason": f"Feed is {feed:.0f}% of revenue — above the recommended range.",
        })
    if opening < revenue / 12 or monthly_cf < 1500:
        actions.append({
            "title": "Build a stronger cash reserve before increasing spending.",
            "reason": "Cash reserves look tight relative to monthly costs.",
        })
    if margin >= 15 and forecast.get("annual_profit", 0) > 0:
        actions.append({
            "title": "Consider using surplus cash to reduce debt or build reserves.",
            "reason": "Profitability is healthy on current assumptions.",
        })
    if loan_pct > 12:
        actions.append({
            "title": "Monitor monthly repayment coverage before taking new loans.",
            "reason": f"Loan repayments are {loan_pct:.0f}% of farm revenue.",
        })
    if forecast.get("risk_level") != "Low":
        actions.append({
            "title": "Run a milk price downside scenario in the Scenario Planner.",
            "reason": "Risk level suggests testing what-if changes before major decisions.",
        })

    for concern in advisory.get("key_concerns", [])[:2]:
        if not any(concern.lower() in a["reason"].lower() for a in actions):
            actions.append({"title": concern, "reason": "Flagged by your farm forecast."})

    if len(actions) < 5:
        defaults = [
            {"title": "Review monthly cashflow and plan for seasonal dips.", "reason": "Routine dairy farm best practice."},
            {"title": "Track milk price trends with your processor.", "reason": "Income sensitivity to milk price is high."},
            {"title": "Compare vet and health costs per cow to last year.", "reason": "Early detection of cost drift."},
        ]
        for d in defaults:
            if len(actions) >= 5:
                break
            if not any(d["title"] == a["title"] for a in actions):
                actions.append(d)

    return [{"rank": i + 1, **a} for i, a in enumerate(actions[:5])]


def _plain_summary(forecast: dict, health: dict, farm: dict) -> str:
    name = forecast.get("farm_name", farm.get("farm_name", "Your farm"))
    profit = forecast.get("annual_profit", 0)
    risk = forecast.get("risk_level", "Medium")
    parts = [
        f"{name} has a farm health score of {health['score']}/100 ({health['label']}).",
    ]
    if profit > 0:
        parts.append(
            f"Based on current assumptions, the farm is forecast to remain profitable "
            f"with €{profit:,.0f} annual profit, but {health['cashflow'].lower()} cashflow "
            f"and {health['feed_pressure'].lower()} feed cost pressure should be monitored."
        )
    else:
        parts.append(
            "The farm may struggle to remain profitable on current figures — "
            "review costs and income assumptions urgently."
        )
    if risk == "High":
        parts.append("Overall risk is elevated — prioritise cash and cost actions this month.")
    elif risk == "Low":
        parts.append("Overall risk is low — stay disciplined on costs while planning ahead.")
    return " ".join(parts)


def get_financial_intelligence(
    farm_id: str | None = None,
    sectors: list[str] | None = None,
) -> dict:
    """Build the full Financial Intelligence payload for the selected farm."""
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    profile = get_farmer_profile(farm_id, selected)
    farm, forecast, extras = _load_forecast_context(farm_file, selected)
    advisory = extras["advisory"]
    risk_drivers = extras["risk_drivers"]
    health = _health_score(forecast, farm)

    risks = []
    for driver in (risk_drivers or [])[:5]:
        risks.append({
            "driver": driver.get("driver", "Risk factor"),
            "severity": driver.get("risk", driver.get("severity", "Medium")),
            "commentary": driver.get("commentary", ""),
        })
    if not risks:
        for alert in forecast.get("alerts", [])[:5]:
            risks.append({"driver": alert, "severity": "Medium", "commentary": ""})

    return {
        "success": True,
        "farm_file": farm_file,
        "farm_name": profile.get("farm_name"),
        "profile": profile,
        "health_score": health,
        "key_strengths": advisory.get("key_strengths", []),
        "key_weaknesses": advisory.get("key_concerns", []),
        "biggest_risks": risks,
        "opportunities": _opportunities(forecast, farm),
        "recommended_actions": _recommended_actions(forecast, farm, advisory),
        "plain_summary": _plain_summary(forecast, health, farm),
        "alerts": forecast.get("alerts", []),
        "forecast_summary": {
            "annual_revenue": forecast.get("annual_revenue"),
            "annual_profit": forecast.get("annual_profit"),
            "profit_margin": forecast.get("profit_margin"),
            "risk_level": forecast.get("risk_level"),
            "monthly_cashflow": forecast.get("monthly_cashflow"),
            "feed_cost_ratio": forecast.get("feed_cost_ratio"),
        },
        "advisor_headline": advisory.get("headline", ""),
    }


def _normalize_question(question: str) -> str:
    return question.strip().lower()


def ask_farm_advisor(
    question: str,
    farm_id: str | None = None,
    sectors: list[str] | None = None,
) -> dict:
    """Rule-based answers to common farmer questions."""
    intel = get_financial_intelligence(farm_id, sectors=sectors)
    forecast = intel["forecast_summary"]
    health = intel["health_score"]
    q = _normalize_question(question)
    details: list[str] = []

    if not q:
        return {
            "success": True,
            "question": question,
            "answer": "Please ask a question about your farm finances, for example: "
            "'Can I afford new machinery?' or 'What are my biggest risks?'",
            "details": [],
        }

    profit = forecast.get("annual_profit", 0) or 0
    monthly_cf = forecast.get("monthly_cashflow", 0) or 0
    opening = intel["profile"].get("opening_cash_balance", 0) or 0
    headroom = opening + max(monthly_cf, 0) * 3
    answer = ""

    if "machinery" in q or ("afford" in q and ("new" in q or "equipment" in q or "machine" in q)):
        if headroom >= 50000 and profit > 20000:
            answer = (
                f"Based on current figures, you may have room for machinery investment "
                f"(roughly €{headroom:,.0f} headroom), but spread payments and keep a cash buffer."
            )
        elif profit > 0:
            answer = (
                "Profit is positive but cash headroom is limited. "
                "Consider delaying large machinery purchases or buying used equipment until reserves improve."
            )
        else:
            answer = "On current figures, new machinery would add pressure — focus on cashflow first."

    elif "milk price" in q and ("fall" in q or "drop" in q or "decrease" in q or "lower" in q):
        answer = (
            "A milk price drop would reduce income directly. "
            "Use the Scenario Planner to test -5c/L or -10% and review the impact on profit and cash."
        )
        details = ["Open Scenario Planner → enter a negative milk price change → Run Scenario."]

    elif "herd" in q and ("increase" in q or "more cow" in q or "expand" in q):
        cows = intel["profile"].get("milking_cows", 120)
        answer = (
            f"Adding cows from your current {cows} increases feed, labour, and housing needs. "
            "Only expand if feed capacity, labour, and cash reserves can support the extra costs."
        )

    elif "cashflow" in q or "cash flow" in q or ("cash" in q and ("weak" in q or "tight" in q or "low" in q)):
        answer = (
            f"Cashflow status: {health['cashflow']}. "
            f"Monthly cashflow averages €{monthly_cf:,.0f}. "
            + (intel.get("advisor_headline") or intel["plain_summary"][:200])
        )

    elif "risk" in q:
        risks = intel.get("biggest_risks", [])
        if risks:
            answer = "Your biggest financial risks right now: " + "; ".join(
                f"{r['driver']} ({r.get('severity', r.get('risk', 'Medium'))})" for r in risks[:5]
            )
        else:
            answer = f"Overall risk level is {forecast.get('risk_level', 'Medium')}. No critical risks flagged."

    elif "feed" in q:
        feed = forecast.get("feed_cost_ratio", 0)
        answer = (
            f"Feed is about {feed:.0f}% of revenue. "
            + ("This is high — review ration and supplier contracts." if feed > 35
               else "This is within a manageable range — keep monitoring.")
        )

    elif "loan" in q or "debt" in q:
        answer = (
            f"Debt pressure is {health['debt_pressure']}. "
            "Monitor monthly repayment coverage before taking new loans."
        )

    elif "profit" in q or "performing" in q:
        answer = (
            f"Annual profit is forecast at €{profit:,.0f} with {forecast.get('profit_margin', 0):.1f}% margin. "
            f"Farm health score: {health['score']}/100 ({health['label']})."
        )

    else:
        answer = (
            f"{intel['plain_summary']} "
            "Try asking about machinery, milk price, herd size, cashflow, or risks."
        )

    return {
        "success": True,
        "question": question,
        "answer": answer,
        "details": details,
    }
