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
from forecast_engine.cashflow_actions import (
    ACTION_LABELS,
    ALL_ACTIONS,
    apply_cashflow_action,
    lowest_balance_and_deficits,
)
from forecast_engine.period_labels import scenario_result as scenario_result_period
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

    # "Buy machinery": a one-off cash purchase is a delta off TODAY's opening
    # cash, not a farmer-guessed absolute figure - so it stays correct
    # regardless of what the farmer's actual current cash position is, and
    # composes with an explicit opening_cash_balance override above (e.g. "my
    # cash is really €X, and I also buy machinery for €Y" nets to X-Y).
    capital_purchase = inputs.get("capital_purchase_amount") or 0
    if capital_purchase:
        base_cash = changes.get("opening_cash_balance", farm.get("opening_cash_balance", 0))
        changes["opening_cash_balance"] = round(float(base_cash) - float(capital_purchase), 2)

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

    if comparison.get("additional_funding_pressure"):
        month = comparison.get("min_cash_month_scenario")
        when = f" around month {month}" if month else ""
        recs.append({
            "title": "This scenario adds cash-shortage pressure",
            "description": f"Cash is projected to run short{when}. Talk to your lender before committing to this change.",
        })
    elif comparison.get("monthly_cashflow_scenario", 0) < 0 or comparison.get("min_cash_scenario", 0) < 0:
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

    def _min_balance_and_month(months: list[dict]) -> tuple[float, Any]:
        if not months:
            return 0.0, None
        worst = min(months, key=lambda m: m.get("running_balance", 0))
        return worst.get("running_balance", 0), worst.get("month")

    def _deficit_months(months: list[dict]) -> int:
        return sum(1 for m in months if m.get("running_balance", 0) < 0)

    def _year_end_cash(months: list[dict], opening: float) -> float:
        return months[-1].get("running_balance", opening) if months else opening

    min_cash_base, min_cash_month_base = _min_balance_and_month(base_monthly)
    min_cash_scenario, min_cash_month_scenario = _min_balance_and_month(scenario_monthly)
    deficit_months_base = _deficit_months(base_monthly)
    deficit_months_scenario = _deficit_months(scenario_monthly)
    year_end_cash_base = _year_end_cash(base_monthly, farm.get("opening_cash_balance", 0))
    year_end_cash_scenario = _year_end_cash(scenario_monthly, farm.get("opening_cash_balance", 0))

    # A scenario adds genuine funding pressure only when it pushes the farm
    # into a cash shortfall it did not already have, or deepens one it did -
    # never merely because the scenario happens to be worse in some other
    # respect (e.g. lower profit with cash always positive is not "funding
    # pressure").
    additional_funding_pressure = min_cash_scenario < 0 and min_cash_scenario < min_cash_base

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
        "min_cash_month_base": min_cash_month_base,
        "min_cash_month_scenario": min_cash_month_scenario,
        "deficit_months_base": deficit_months_base,
        "deficit_months_scenario": deficit_months_scenario,
        "year_end_cash_base": year_end_cash_base,
        "year_end_cash_scenario": year_end_cash_scenario,
        "additional_funding_pressure": additional_funding_pressure,
        "risk_base": base_result.get("risk_level"),
        "risk_scenario": scenario_result.get("risk_level"),
        "period": scenario_result_period(),
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


def _cashflow_action_params(inputs: dict) -> dict:
    params = {}
    for key in ("amount", "from_month", "to_month", "payment_month", "draw_month", "repay_month", "annual_rate"):
        value = inputs.get(key)
        if value is not None and value != "":
            params[key] = value
    return params


def run_cashflow_action(
    farm_file: str,
    action: str,
    inputs: dict | None = None,
    sectors: list[str] | None = None,
) -> dict:
    """Test one of the 5 practical cash-flow actions (Teagasc item 6).

    Reuses the farm+household-aware `monthly_forecast` already computed by
    `services/multi_sector_farm.py` (Phases 2-3) rather than re-running the
    forecast engine, then reports the resulting lowest cash balance and
    number of deficit months — the two metrics the document asks for.
    """
    if action not in ALL_ACTIONS:
        raise ValueError(f"Unknown cash-flow action: {action}. Choose one of {sorted(ALL_ACTIONS)}.")

    inputs = inputs or {}
    resolved_sectors = resolve_sectors(sectors, farm_file) if sectors else resolve_sectors(None, farm_file)
    farm = load_farm_for_analysis(farm_file, resolved_sectors)
    base_monthly = farm.get("monthly_forecast") or []

    params = _cashflow_action_params(inputs)
    scenario_monthly, description = apply_cashflow_action(action, base_monthly, **params)

    base_metrics = lowest_balance_and_deficits(base_monthly)
    scenario_metrics = lowest_balance_and_deficits(scenario_monthly)

    return {
        "success": True,
        "farm_file": farm_file,
        "farm_name": farm.get("farm_name"),
        "action": action,
        "label": ACTION_LABELS.get(action, action),
        "description": description,
        "lowest_balance_base": base_metrics["lowest_balance"],
        "lowest_balance_scenario": scenario_metrics["lowest_balance"],
        "lowest_balance_month_base": base_metrics["lowest_balance_month"],
        "lowest_balance_month_scenario": scenario_metrics["lowest_balance_month"],
        "deficit_months_base": base_metrics["deficit_months"],
        "deficit_months_scenario": scenario_metrics["deficit_months"],
        "improvement": round(scenario_metrics["lowest_balance"] - base_metrics["lowest_balance"], 2),
        "monthly_forecast_base": base_monthly,
        "monthly_forecast_scenario": scenario_monthly,
        "period": scenario_result_period(),
    }


def run_all_cashflow_actions(
    farm_file: str,
    sectors: list[str] | None = None,
) -> dict:
    """Test all 5 practical cash-flow actions with auto-detected defaults."""
    resolved_sectors = resolve_sectors(sectors, farm_file) if sectors else resolve_sectors(None, farm_file)
    farm = load_farm_for_analysis(farm_file, resolved_sectors)
    base_monthly = farm.get("monthly_forecast") or []
    base_metrics = lowest_balance_and_deficits(base_monthly)

    results = []
    for action in ALL_ACTIONS:
        scenario_monthly, description = apply_cashflow_action(action, base_monthly)
        scenario_metrics = lowest_balance_and_deficits(scenario_monthly)
        results.append({
            "action": action,
            "label": ACTION_LABELS.get(action, action),
            "description": description,
            "lowest_balance_base": base_metrics["lowest_balance"],
            "lowest_balance_scenario": scenario_metrics["lowest_balance"],
            "deficit_months_base": base_metrics["deficit_months"],
            "deficit_months_scenario": scenario_metrics["deficit_months"],
            "improvement": round(scenario_metrics["lowest_balance"] - base_metrics["lowest_balance"], 2),
        })

    return {
        "success": True,
        "farm_file": farm_file,
        "farm_name": farm.get("farm_name"),
        "base_lowest_balance": base_metrics["lowest_balance"],
        "base_deficit_months": base_metrics["deficit_months"],
        "results": results,
        "period": scenario_result_period(),
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
