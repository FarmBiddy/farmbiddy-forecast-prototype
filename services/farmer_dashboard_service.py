"""
FarmBiddy Farmer Edition — dashboard service wrapping the existing forecast engine.

Does not duplicate forecast calculations; orchestrates run_forecast, sandbox,
advisory, and chart generation for the single active farm profile.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.paths import FARM_PROFILE_PATH
from forecast_engine.revenue import calculate_revenue
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.alerts import generate_alerts
from forecast_engine.cashflow import calculate_monthly_cashflow
from models.api_models import ForecastOutputs, SandboxOutputs
from services.forecast_service import (
    apply_sandbox_changes,
    load_farm,
    list_available_farms,
    run_forecast,
    run_sandbox_forecast,
)
from forecast_engine.monte_carlo import run_monte_carlo
from forecast_engine.scenarios import calculate_scenarios


DEFAULT_FARM_FILE = "dairy_farm_1.json"


def _load_profile_config() -> dict:
    if os.path.exists(FARM_PROFILE_PATH):
        with open(FARM_PROFILE_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    return {
        "active_farm_file": DEFAULT_FARM_FILE,
        "farm_display_name": "Green Valley Dairy",
        "milk_processor": "Lakeland Dairies",
    }


def get_active_farm_file() -> str:
    return _load_profile_config().get("active_farm_file", DEFAULT_FARM_FILE)


def resolve_farm_file(farm_id: str | None = None) -> str:
    if farm_id:
        return farm_id if farm_id.endswith(".json") else f"{farm_id}.json"
    return get_active_farm_file()


def list_farms_for_selector() -> list[dict]:
    farms = list_available_farms()
    default = get_active_farm_file()
    for farm in farms:
        farm["is_default"] = farm["farm_file"] == default
    return farms


def get_farmer_profile(farm_id: str | None = None) -> dict:
    """Return profile for the selected or default farm."""
    config = _load_profile_config()
    farm_file = resolve_farm_file(farm_id)
    farm = load_farm(farm_file)
    display_name = farm.get("farm_name", "My Farm")
    if farm_file == config.get("active_farm_file") and config.get("farm_display_name"):
        display_name = config["farm_display_name"]
    return {
        "success": True,
        "farm_file": farm_file,
        "farm_name": display_name,
        "milking_cows": farm.get("milking_cows"),
        "litres_per_cow": farm.get("litres_per_cow"),
        "milk_price": farm.get("milk_price"),
        "opening_cash_balance": farm.get("opening_cash_balance"),
        "milk_processor": config.get("milk_processor", "Lakeland Dairies") if farm_file == config.get("active_farm_file") else "—",
        "location": config.get("location", ""),
        "owner_name": config.get("owner_name", "Farmer"),
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
    }


def _risk_to_score(risk_level: str) -> int:
    mapping = {"Low": 78, "Medium": 58, "High": 35}
    return mapping.get(risk_level or "", 65)


def _health_breakdown(forecast: dict, farm: dict) -> dict:
    margin = forecast.get("profit_margin", 0)
    risk = forecast.get("risk_level", "Medium")
    profit_label = "Good" if margin >= 15 else ("Fair" if margin >= 8 else "Watch")
    liquidity_label = "Good"
    monthly_cf = forecast.get("monthly_cashflow", 0)
    if monthly_cf < 0:
        liquidity_label = "Tight"
    elif monthly_cf < 2000:
        liquidity_label = "Fair"
    return {
        "score": _risk_to_score(risk),
        "label": "Good" if _risk_to_score(risk) >= 70 else ("Fair" if _risk_to_score(risk) >= 50 else "Needs attention"),
        "profitability": profit_label,
        "liquidity": liquidity_label,
        "solvency": "Good" if risk != "High" else "Watch",
        "efficiency": "Good" if forecast.get("feed_cost_ratio", 100) < 35 else "Fair",
    }


def _build_kpis(forecast: dict, farm: dict) -> List[dict]:
    summary = forecast.get("forecast_summary") or {}
    kpis_block = forecast.get("kpis") or {}
    monthly = summary.get("annual_profit", 0) / 12 if summary else 0
    monthly_cf = kpis_block.get("monthly_cashflow", monthly)
    feed_pct = kpis_block.get("feed_cost_ratio", forecast.get("feed_cost_ratio", 31))
    risk = forecast.get("risk_level", "Low")
    cash = farm.get("opening_cash_balance", 0)
    monthly_forecast = forecast.get("monthly_forecast") or []
    if monthly_forecast:
        cash = monthly_forecast[-1].get("running_balance", cash)

    return [
        {
            "id": "cash",
            "title": "Cash Available",
            "value": f"€{cash:,.0f}",
            "subtitle": f"+ €{max(monthly_cf, 0):,.0f} this month",
            "trend": "up" if monthly_cf >= 0 else "down",
        },
        {
            "id": "milk_price",
            "title": "Milk Price",
            "value": f"€{farm.get('milk_price', 0.42):.2f} / L",
            "subtitle": "No change",
            "trend": "neutral",
        },
        {
            "id": "profit",
            "title": "Expected Monthly Profit",
            "value": f"€{monthly:,.0f}",
            "subtitle": f"Annual €{summary.get('annual_profit', 0):,.0f}",
            "trend": "up" if monthly > 0 else "down",
        },
        {
            "id": "risk",
            "title": "Risk Level",
            "value": risk or "Low",
            "subtitle": "Stable" if risk == "Low" else "Monitor closely",
            "trend": "neutral",
        },
        {
            "id": "feed",
            "title": "Feed Cost %",
            "value": f"{feed_pct:.0f}%",
            "subtitle": "Good" if feed_pct < 35 else "High",
            "trend": "neutral",
        },
    ]


def _build_recommendations(forecast: dict) -> List[dict]:
    advisory = forecast.get("advisory_summary") or {}
    actions: List[dict] = []
    concerns = advisory.get("key_concerns") or []
    for i, concern in enumerate(concerns[:5]):
        actions.append({"rank": i + 1, "title": concern, "description": ""})
    if advisory.get("advisor_recommendation"):
        actions.append({
            "rank": len(actions) + 1,
            "title": advisory["advisor_recommendation"],
            "description": advisory.get("risk_commentary", ""),
        })
    if len(actions) < 5:
        defaults = [
            "Consider locking in feed prices before the next increase.",
            "Monitor cash reserves for tight months ahead.",
            "Improve milk yield by 0.5 L/cow/day to increase profit.",
            "Review labour costs and working efficiency.",
            "Delay non-essential machinery investment if cash is tight.",
        ]
        for item in defaults:
            if len(actions) >= 5:
                break
            if not any(a["title"] == item for a in actions):
                actions.append({"rank": len(actions) + 1, "title": item, "description": ""})
    return actions[:5]


def _scenario_snapshot(
    farm_file: str,
    label: str,
    changes: dict,
    base_profit: float,
) -> dict:
    outputs = SandboxOutputs(forecast_summary=True, risk_level=True, kpis=True)
    try:
        result = run_sandbox_forecast(farm_file, changes, outputs)
        profit = (result.get("forecast_summary") or {}).get("annual_profit", 0)
        diff = profit - base_profit
        impact = "positive" if diff >= 0 else "negative impact"
        return {
            "label": label,
            "annual_profit": profit,
            "profit_impact": impact,
            "profit_difference": round(diff, 0),
            "risk_level": result.get("risk_level", "Medium"),
        }
    except Exception:
        return {"label": label, "annual_profit": base_profit, "profit_impact": "unknown", "risk_level": "Medium"}


def _build_scenario_snapshots(farm_file: str, base_profit: float, farm: dict) -> List[dict]:
    milk_change = {"milk_price": round(farm["milk_price"] * 0.9, 4)}
    feed_change = {"feed": round(farm["feed"] * 1.15, 2)}
    return [
        _scenario_snapshot(farm_file, "Milk Price -10%", milk_change, base_profit),
        _scenario_snapshot(farm_file, "Feed Cost +15%", feed_change, base_profit),
        {
            "label": "Base Case",
            "annual_profit": base_profit,
            "profit_impact": "positive",
            "profit_difference": 0,
            "risk_level": "Low",
        },
    ]


def _fallback_kpis(farm: dict) -> List[dict]:
    """Demo-style KPIs before the first analysis run."""
    revenue = calculate_revenue(farm)
    costs = calculate_costs(farm)
    profit = calculate_profit(revenue, costs)
    monthly = profit / 12
    monthly_cf = calculate_monthly_cashflow(revenue, costs)
    feed_ratio = (farm.get("feed", 0) / revenue * 100) if revenue else 31
    alerts = generate_alerts(farm, profit, revenue, costs, monthly_cf)
    risk = calculate_risk_level(alerts, profit / revenue if revenue else 0)
    cash = farm.get("opening_cash_balance", 10000) + monthly

    return [
        {"id": "cash", "title": "Cash Available", "value": f"€{cash:,.0f}", "subtitle": f"+ €{max(monthly_cf, 0):,.0f} this month", "trend": "up"},
        {"id": "milk_price", "title": "Milk Price", "value": f"€{farm.get('milk_price', 0.42):.2f} / L", "subtitle": "No change", "trend": "neutral"},
        {"id": "profit", "title": "Expected Monthly Profit", "value": f"€{monthly:,.0f}", "subtitle": f"Annual €{profit:,.0f}", "trend": "up"},
        {"id": "risk", "title": "Risk Level", "value": risk, "subtitle": "Stable" if risk == "Low" else "Monitor", "trend": "neutral"},
        {"id": "feed", "title": "Feed Cost %", "value": f"{feed_ratio:.0f}%", "subtitle": "Good" if feed_ratio < 35 else "High", "trend": "neutral"},
    ]


def run_farmer_analysis(farm_id: str | None = None, save_result: bool = True) -> dict:
    """Run full forecast + charts + farmer dashboard payload for the selected farm."""
    farm_file = resolve_farm_file(farm_id)
    farm = load_farm(farm_file)
    profile = get_farmer_profile(farm_id)

    outputs = ForecastOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        top_risk_drivers=True,
        profitability_dashboard=True,
        advisory_summary=True,
        kpis=True,
        scenarios=True,
    )

    forecast = run_forecast(
        farm_file=farm_file,
        outputs=outputs,
        save_result=save_result,
        generate_charts=True,
        chart_types=["running_balance", "revenue_vs_costs", "cost_breakdown", "scenario_profit"],
    )

    summary = forecast.get("forecast_summary") or {}
    base_profit = summary.get("annual_profit", 0)
    monthly_forecast = forecast.get("monthly_forecast") or []

    upcoming = [{
        "label": "Loan repayment",
        "amount": round(farm.get("loan_repayments", 36000) / 12, 0),
        "frequency": "Monthly",
        "due": "This month",
    }]

    return {
        "success": True,
        "generated_at": forecast.get("generated_at"),
        "profile": profile,
        "kpis": _build_kpis(forecast, farm),
        "alerts": forecast.get("alerts") or [],
        "recommendations": _build_recommendations(forecast),
        "health": _health_breakdown(
            {
                "profit_margin": summary.get("profit_margin", 0),
                "risk_level": forecast.get("risk_level"),
                "monthly_cashflow": (forecast.get("kpis") or {}).get("monthly_cashflow", 0),
                "feed_cost_ratio": (forecast.get("kpis") or {}).get("feed_cost_ratio", 31),
            },
            farm,
        ),
        "scenario_snapshots": _build_scenario_snapshots(farm_file, base_profit, farm),
        "charts": forecast.get("charts") or {},
        "monthly_forecast": monthly_forecast,
        "profit_chart_data": [
            {"month": m.get("month"), "profit": m.get("cashflow"), "revenue": m.get("revenue"), "costs": m.get("costs")}
            for m in monthly_forecast
        ],
        "cashflow_chart_data": [
            {"month": m.get("month"), "cash_in": m.get("revenue"), "cash_out": m.get("costs"), "net": m.get("cashflow"), "balance": m.get("running_balance")}
            for m in monthly_forecast
        ],
        "recent_updates": [{
            "label": "Forecast run",
            "detail": f"Annual profit €{base_profit:,.0f}",
            "when": forecast.get("generated_at", "")[:10],
        }],
        "upcoming_payments": upcoming,
        "forecast_summary": summary,
        "top_risk_drivers": forecast.get("top_risk_drivers") or [],
    }


def get_farmer_dashboard_preview(farm_id: str | None = None) -> dict:
    """Dashboard shell with profile and fallback KPIs before Run Analysis."""
    farm_file = resolve_farm_file(farm_id)
    farm = load_farm(farm_file)
    profile = get_farmer_profile(farm_id)
    return {
        "success": True,
        "profile": profile,
        "kpis": _fallback_kpis(farm),
        "has_analysis": False,
        "farms": list_farms_for_selector(),
    }


def run_advanced_forecast(farm_id: str | None = None) -> dict:
    """Advanced forecast with scenarios, Monte Carlo, and farmer interpretation."""
    farm_file = resolve_farm_file(farm_id)
    farm = load_farm(farm_file)
    profile = get_farmer_profile(farm_id)

    outputs = ForecastOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        top_risk_drivers=True,
        profitability_dashboard=True,
        advisory_summary=True,
        kpis=True,
        scenarios=True,
    )

    forecast = run_forecast(
        farm_file=farm_file,
        outputs=outputs,
        save_result=True,
        generate_charts=True,
        chart_types=["running_balance", "revenue_vs_costs", "cost_breakdown", "scenario_profit"],
    )

    summary = forecast.get("forecast_summary") or {}
    monthly = forecast.get("monthly_forecast") or []
    scenarios = calculate_scenarios(farm)
    monte = run_monte_carlo(farm, iterations=1000)

    advisory = forecast.get("advisory_summary") or {}
    interpretation = monte.get("interpretation", "")
    if advisory.get("headline"):
        interpretation = f"{advisory['headline']} {interpretation}"

    return {
        "success": True,
        "farm_file": farm_file,
        "profile": profile,
        "generated_at": forecast.get("generated_at"),
        "forecast_summary": summary,
        "monthly_forecast": monthly,
        "profitability_dashboard": forecast.get("profitability_dashboard"),
        "kpis": forecast.get("kpis"),
        "alerts": forecast.get("alerts") or [],
        "risk_level": forecast.get("risk_level"),
        "top_risk_drivers": forecast.get("top_risk_drivers") or [],
        "advisory_summary": advisory,
        "scenarios": scenarios,
        "monte_carlo": monte,
        "charts": forecast.get("charts") or {},
        "interpretation": interpretation,
        "recommendations": _build_recommendations(forecast),
        "cashflow_chart_data": [
            {"month": m.get("month"), "cash_in": m.get("revenue"), "cash_out": m.get("costs"), "net": m.get("cashflow"), "balance": m.get("running_balance")}
            for m in monthly
        ],
        "profit_chart_data": [
            {"month": m.get("month"), "profit": m.get("cashflow"), "revenue": m.get("revenue"), "costs": m.get("costs")}
            for m in monthly
        ],
    }


def run_monte_carlo_for_farm(farm_id: str | None = None, iterations: int = 1000) -> dict:
    """Run Monte Carlo simulation for the selected farm."""
    farm_file = resolve_farm_file(farm_id)
    farm = load_farm(farm_file)
    profile = get_farmer_profile(farm_id)
    monte = run_monte_carlo(farm, iterations=iterations)
    return {
        "success": True,
        "farm_file": farm_file,
        "profile": profile,
        "monte_carlo": monte,
        "scenarios": calculate_scenarios(farm),
    }
