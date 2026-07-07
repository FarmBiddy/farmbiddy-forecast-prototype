"""
Scenario sandbox — compare base case vs changed assumptions with farmer recommendations.
"""

from __future__ import annotations

from typing import Any

from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.revenue import calculate_revenue
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.alerts import generate_alerts
from models.api_models import ForecastOutputs, SandboxOutputs
from services.farmer_dashboard_service import resolve_sectors
from services.forecast_service import load_farm, run_forecast, run_sandbox_forecast
from services.multi_sector_farm import load_farm_for_analysis


def resolve_farm_file(farm_id: str | None) -> str:
    if not farm_id:
        from services.farmer_dashboard_service import get_active_farm_file
        return get_active_farm_file()
    if not farm_id.endswith(".json"):
        farm_id = f"{farm_id}.json"
    return farm_id


def build_absolute_changes(farm: dict, inputs: dict) -> dict[str, Any]:
    """Convert sandbox UI inputs (cents, %, absolutes) into farm field values."""
    changes: dict[str, Any] = {}

    cents = inputs.get("milk_price_cents_change") or 0
    pct_milk = inputs.get("milk_price_pct_change") or 0
    if cents:
        changes["milk_price"] = round(float(farm["milk_price"]) + float(cents) / 100, 4)
    elif pct_milk:
        changes["milk_price"] = round(float(farm["milk_price"]) * (1 + float(pct_milk) / 100), 4)

    pct_map = {
        "feed_pct_change": "feed",
        "fertiliser_pct_change": "fertiliser",
        "labour_pct_change": "labour",
        "vet_pct_change": "vet",
        "fuel_pct_change": "fuel",
        "electricity_pct_change": "electricity",
    }
    for input_key, field in pct_map.items():
        pct = inputs.get(input_key) or 0
        if pct:
            base = float(farm.get(field, farm.get("contractor", 0) if field == "fuel" else 0))
            changes[field] = round(base * (1 + float(pct) / 100), 2)

    for field in ("loan_repayments", "milking_cows", "litres_per_cow", "opening_cash_balance"):
        if inputs.get(field) is not None and inputs[field] != "":
            val = inputs[field]
            changes[field] = int(val) if field == "milking_cows" else float(val)

    return changes


def build_scenario_recommendations(
    base: dict,
    scenario: dict,
    changes: dict,
    comparison: dict,
) -> list[dict]:
    """Generate practical recommendations from scenario comparison."""
    recs: list[dict] = []
    profit_diff = comparison.get("profit_difference", 0)
    risk_base = base.get("risk_level", "Medium")
    risk_scenario = scenario.get("risk_level", "Medium")

    if "milk_price" in changes:
        if profit_diff > 0:
            recs.append({
                "title": "Higher milk price improves outlook",
                "description": "Consider building cash reserves before increasing spending.",
            })
        else:
            recs.append({
                "title": "Lower milk price reduces margin",
                "description": "Review cost control and defer non-essential purchases.",
            })

    if "feed" in changes or any(k.startswith("feed") for k in changes):
        if profit_diff < 0:
            recs.append({
                "title": "Feed costs are squeezing profit",
                "description": "Review suppliers, ration efficiency, and grazing plans.",
            })

    if comparison.get("monthly_cashflow_scenario", 0) < 0 or comparison.get("min_cash_scenario", 0) < 0:
        recs.append({
            "title": "Cashflow may become negative",
            "description": "Delay machinery purchases and monitor monthly bills closely.",
        })

    if "milking_cows" in changes:
        delta = changes["milking_cows"].get("to", 0) - changes["milking_cows"].get("from", 0)
        if delta > 0:
            recs.append({
                "title": "Herd expansion needs capacity check",
                "description": "Confirm feed, labour, and housing can support more cows.",
            })

    if "loan_repayments" in changes:
        recs.append({
            "title": "Loan repayments affect monthly cash",
            "description": "Monitor monthly cash coverage against loan and operating costs.",
        })

    if risk_scenario != risk_base and risk_scenario == "High":
        recs.append({
            "title": "Risk level has increased",
            "description": "Review the scenario with your adviser and agree protective actions.",
        })

    if not recs:
        recs.append({
            "title": "Scenario impact is limited",
            "description": "Current changes do not materially shift farm risk — keep monitoring.",
        })

    return [{"rank": i + 1, **r} for i, r in enumerate(recs[:5])]


def run_scenario_sandbox(
    farm_file: str,
    inputs: dict,
    sectors: list[str] | None = None,
) -> dict:
    """Run base vs scenario comparison with recommendations."""
    payload = dict(inputs)
    if sectors is None:
        sectors = payload.pop("sectors", None)
    else:
        payload.pop("sectors", None)

    resolved_sectors = resolve_sectors(sectors, farm_file) if sectors else None
    if resolved_sectors:
        farm = load_farm_for_analysis(farm_file, resolved_sectors)
    else:
        farm = load_farm(farm_file)
    absolute = build_absolute_changes(farm, payload)

    outputs = SandboxOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        kpis=True,
        advisory_summary=True,
    )

    base_result = run_sandbox_forecast(farm_file, {}, outputs, sectors=resolved_sectors)
    scenario_result = (
        run_sandbox_forecast(farm_file, absolute, outputs, sectors=resolved_sectors)
        if absolute
        else base_result
    )

    base_summary = base_result.get("forecast_summary") or {}
    scenario_summary = scenario_result.get("forecast_summary") or {}
    base_kpis = base_result.get("kpis") or {}
    scenario_kpis = scenario_result.get("kpis") or {}

    base_monthly = base_result.get("monthly_forecast") or []
    scenario_monthly = scenario_result.get("monthly_forecast") or []
    min_cash_base = min((m.get("running_balance", 0) for m in base_monthly), default=0)
    min_cash_scenario = min((m.get("running_balance", 0) for m in scenario_monthly), default=0)

    comparison = {
        "revenue_base": base_summary.get("annual_revenue", 0),
        "revenue_scenario": scenario_summary.get("annual_revenue", 0),
        "revenue_difference": round(scenario_summary.get("annual_revenue", 0) - base_summary.get("annual_revenue", 0), 0),
        "profit_base": base_summary.get("annual_profit", 0),
        "profit_scenario": scenario_summary.get("annual_profit", 0),
        "profit_difference": round(scenario_summary.get("annual_profit", 0) - base_summary.get("annual_profit", 0), 0),
        "monthly_profit_base": round(base_summary.get("annual_profit", 0) / 12, 0),
        "monthly_profit_scenario": round(scenario_summary.get("annual_profit", 0) / 12, 0),
        "monthly_cashflow_base": base_kpis.get("monthly_cashflow", 0),
        "monthly_cashflow_scenario": scenario_kpis.get("monthly_cashflow", 0),
        "min_cash_base": min_cash_base,
        "min_cash_scenario": min_cash_scenario,
        "risk_base": base_result.get("risk_level"),
        "risk_scenario": scenario_result.get("risk_level"),
    }

    changes_applied = scenario_result.get("changes_applied") or {}

    summary_text = _plain_summary(comparison, absolute)

    recommendations = build_scenario_recommendations(
        base_result, scenario_result, changes_applied, comparison
    )

    return {
        "success": True,
        "farm_file": farm_file,
        "farm_name": farm.get("farm_name"),
        "changes_applied": changes_applied,
        "comparison": comparison,
        "summary": summary_text,
        "recommendations": recommendations,
        "base": {
            "forecast_summary": base_summary,
            "risk_level": base_result.get("risk_level"),
            "kpis": base_kpis,
        },
        "scenario": {
            "forecast_summary": scenario_summary,
            "risk_level": scenario_result.get("risk_level"),
            "kpis": scenario_kpis,
        },
        "monthly_forecast_base": base_monthly,
        "monthly_forecast_scenario": scenario_monthly,
    }


def _plain_summary(comparison: dict, changes: dict) -> str:
    diff = comparison.get("profit_difference", 0)
    if not changes:
        return "No changes applied — showing your current farm plan."
    if diff > 5000:
        return f"This scenario could improve annual profit by about €{diff:,.0f}."
    if diff < -5000:
        return f"This scenario could reduce annual profit by about €{abs(diff):,.0f}."
    return "This scenario has a moderate impact on profit — review cashflow and risk carefully."
