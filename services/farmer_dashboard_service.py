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

from config.paths import DATASETS_DIR, FARM_PROFILE_PATH
from forecast_engine.revenue import calculate_revenue
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.alerts import generate_alerts
from forecast_engine.cashflow import calculate_monthly_cashflow
from models.api_models import ForecastOutputs, SandboxOutputs
from services.forecast_service import (
    apply_sandbox_changes,
    list_available_farms,
    load_farm,
    run_forecast,
    run_sandbox_forecast,
)
from services.multi_sector_farm import (
    MULTI_SECTOR_FILE,
    is_multi_sector,
    list_sectors_for_selector,
    load_farm_for_analysis,
    load_multi_sector_farm,
    parse_sectors_param,
)
from forecast_engine.monte_carlo import run_monte_carlo
from forecast_engine.scenarios import calculate_scenarios
from services.dashboard_summary import (
    build_executive_dashboard,
    calculate_preview_kpis,
    get_historical_data,
    get_selected_sector_data,
)


DEFAULT_FARM_FILE = MULTI_SECTOR_FILE


def _load_profile_config() -> dict:
    if os.path.exists(FARM_PROFILE_PATH):
        with open(FARM_PROFILE_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    return {
        "active_farm_file": DEFAULT_FARM_FILE,
        "farm_display_name": "Knockrow Mixed Farm",
        "milk_processor": "Lakeland Dairies",
    }


def get_active_farm_file() -> str:
    return _load_profile_config().get("active_farm_file", DEFAULT_FARM_FILE)


def resolve_farm_file(farm_id: str | None = None) -> str:
    if farm_id:
        filename = farm_id if farm_id.endswith(".json") else f"{farm_id}.json"
        path = os.path.join(DATASETS_DIR, filename)
        if os.path.exists(path):
            return filename
        return DEFAULT_FARM_FILE
    return get_active_farm_file()


def resolve_sectors(
    sectors: list[str] | str | None = None,
    farm_id: str | None = None,
) -> list[str]:
    farm_file = resolve_farm_file(farm_id)
    try:
        raw = load_multi_sector_farm(farm_file)
    except (FileNotFoundError, ValueError):
        return parse_sectors_param(sectors, None)
    return parse_sectors_param(sectors, raw)


def get_sectors_list(farm_id: str | None = None, sectors: list[str] | str | None = None) -> dict:
    farm_file = resolve_farm_file(farm_id)
    raw = load_multi_sector_farm(farm_file)
    selected = resolve_sectors(sectors, farm_id)
    return {
        "farm_file": farm_file,
        "farm_name": raw.get("farm_name", "Farm"),
        "available_sectors": list_sectors_for_selector(raw, selected),
        "selected_sectors": selected,
    }


def list_farms_for_selector() -> list[dict]:
    farms = list_available_farms()
    default = get_active_farm_file()
    for farm in farms:
        farm["is_default"] = farm["farm_file"] == default
    return farms


def _resolve_owner_name(farm_file: str, config: dict) -> str:
    """Prefer farmer name from dataset JSON, then config, then generic fallback."""
    try:
        raw = load_farm(farm_file)
        farmer = (raw.get("identity") or {}).get("farmer") or {}
        if farmer.get("name"):
            return str(farmer["name"])
        if raw.get("owner_name"):
            return str(raw["owner_name"])
    except (FileNotFoundError, ValueError, OSError):
        pass
    if farm_file == config.get("active_farm_file") and config.get("owner_name"):
        return str(config["owner_name"])
    return "Farmer"


def get_farmer_profile(
    farm_id: str | None = None,
    sectors: list[str] | str | None = None,
) -> dict:
    """Return profile for the selected or default farm."""
    config = _load_profile_config()
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    farm = load_farm_for_analysis(farm_file, selected)
    display_name = farm.get("farm_name", "My Farm")
    if farm_file == config.get("active_farm_file") and config.get("farm_display_name"):
        display_name = config["farm_display_name"]

    raw: dict | None = None
    try:
        if is_multi_sector(_read_farm_json_for_profile(farm_file)):
            raw = load_multi_sector_farm(farm_file)
    except (FileNotFoundError, ValueError):
        raw = None

    processor = "—"
    if farm_file == config.get("active_farm_file"):
        processor = config.get("milk_processor", "Lakeland Dairies")
    elif raw:
        processor = raw.get("sectors", {}).get("dairy", {}).get("processor", "—")

    identity = (raw or {}).get("identity") or {}
    location_block = identity.get("location") or {}
    farmer_block = identity.get("farmer") or {}
    summary = (raw or {}).get("farm_summary") or {}
    county = location_block.get("county") or config.get("location", "")
    owner_name = _resolve_owner_name(farm_file, config)
    if farmer_block.get("name") and not (
        farm_file == config.get("active_farm_file") and config.get("owner_name")
    ):
        owner_name = farmer_block.get("name")

    sector_metrics = farm.get("_sector_metrics") or {}
    dairy_metrics = sector_metrics.get("dairy") or {}
    beef_metrics = sector_metrics.get("beef") or {}
    lamb_metrics = sector_metrics.get("lamb") or {}
    dairy_sector = (raw or {}).get("sectors", {}).get("dairy", {}) if raw else {}
    beef_sector = (raw or {}).get("sectors", {}).get("beef", {}) if raw else {}
    lamb_sector = (raw or {}).get("sectors", {}).get("lamb", {}) if raw else {}
    dairy_herd = dairy_sector.get("herd") or {}
    beef_herd = beef_sector.get("herd") or {}
    lamb_flock = lamb_sector.get("flock") or {}
    dairy_pricing = dairy_sector.get("pricing") or {}

    sector_profile: dict[str, dict] = {}
    if "dairy" in selected:
        sector_profile["dairy"] = {
            "milking_cows": dairy_metrics.get("milking_cows") or farm.get("milking_cows"),
            "litres_per_cow": dairy_metrics.get("litres_per_cow") or farm.get("litres_per_cow"),
            "annual_milk_litres": dairy_metrics.get("annual_milk_litres"),
            "milk_price": dairy_metrics.get("milk_price") or farm.get("milk_price"),
            "processor": processor,
            "dry_cows": dairy_herd.get("dry_cows"),
            "replacement_heifers": dairy_herd.get("replacement_heifers"),
            "calves": dairy_herd.get("calves"),
            "milk_solids_bonus_per_litre": float(
                dairy_pricing.get("milk_solids_bonus_per_litre") or 0
            ),
        }
    if "beef" in selected:
        sector_profile["beef"] = {
            "cattle_on_farm": beef_metrics.get("cattle_on_farm"),
            "finishing_units": beef_herd.get("finishing_units"),
            "avg_sale_price_per_head": beef_metrics.get("avg_sale_price_per_head"),
        }
    if "lamb" in selected:
        sector_profile["lamb"] = {
            "ewes": lamb_metrics.get("ewes"),
            "lambs_on_farm": lamb_flock.get("lambs"),
            "avg_lamb_price_per_kg": lamb_metrics.get("avg_lamb_price_per_kg"),
            "lambs_sold_trailing_12": lamb_metrics.get("lambs_sold_trailing_12"),
        }

    land_by_sector = summary.get("land_by_sector") or {}

    return {
        "success": True,
        "farm_file": farm_file,
        "farm_name": display_name,
        "milking_cows": farm.get("milking_cows"),
        "litres_per_cow": farm.get("litres_per_cow"),
        "milk_price": farm.get("milk_price"),
        "opening_cash_balance": farm.get("opening_cash_balance"),
        "milk_processor": processor,
        "location": county,
        "county": county,
        "herd_number": location_block.get("herd_number"),
        "total_hectares": summary.get("total_hectares"),
        "land_by_sector": land_by_sector,
        "owner_name": owner_name,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "selected_sectors": selected,
        "farm_type": farm.get("farm_type", "Mixed"),
        "sector_profile": sector_profile,
    }


def _read_farm_json_for_profile(farm_file: str) -> dict:
    path = os.path.join(DATASETS_DIR, farm_file)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


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
    visibility = forecast.get("kpi_visibility") or farm.get("kpi_visibility") or {}
    monthly = summary.get("annual_profit", 0) / 12 if summary else 0
    monthly_cf = kpis_block.get("monthly_cashflow", monthly)
    feed_pct = kpis_block.get("feed_cost_ratio", forecast.get("feed_cost_ratio", 31))
    risk = forecast.get("risk_level", "Low")
    cash = farm.get("opening_cash_balance", 0)
    monthly_forecast = forecast.get("monthly_forecast") or []
    if monthly_forecast:
        cash = monthly_forecast[-1].get("running_balance", cash)

    cards = [
        {
            "id": "cash",
            "title": "Cash Available",
            "value": f"€{cash:,.0f}",
            "subtitle": f"+ €{max(monthly_cf, 0):,.0f} this month",
            "trend": "up" if monthly_cf >= 0 else "down",
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
    if visibility.get("milk_price", False):
        cards.insert(1, {
            "id": "milk_price",
            "title": "Milk Price",
            "value": f"€{farm.get('milk_price', 0.42):.2f} / L",
            "subtitle": "Dairy sector",
            "trend": "neutral",
        })
    sector_metrics = farm.get("_sector_metrics") or {}
    if visibility.get("beef") and sector_metrics.get("beef"):
        beef = sector_metrics["beef"]
        cards.append({
            "id": "beef_price",
            "title": "Beef Sale Price",
            "value": f"€{beef.get('avg_sale_price_per_head', 0):,.0f} / head",
            "subtitle": f"{beef.get('cattle_on_farm', 0)} cattle on farm",
            "trend": "neutral",
        })
    if visibility.get("lamb") and sector_metrics.get("lamb"):
        lamb = sector_metrics["lamb"]
        cards.append({
            "id": "lamb_price",
            "title": "Lamb Price",
            "value": f"€{lamb.get('avg_lamb_price_per_kg', 0):.2f} / kg",
            "subtitle": f"{lamb.get('ewes', 0)} ewes",
            "trend": "neutral",
        })
    return cards


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
    snapshots = []
    selected = farm.get("_selected_sectors") or ["dairy", "beef", "lamb"]
    if "dairy" in selected and farm.get("milk_price"):
        milk_change = {"milk_price": round(farm["milk_price"] * 0.9, 4)}
        snapshots.append(_scenario_snapshot(farm_file, "Milk Price -10%", milk_change, base_profit))
    feed_change = {"feed": round(farm.get("feed", 0) * 1.15, 2)}
    snapshots.append(_scenario_snapshot(farm_file, "Feed Cost +15%", feed_change, base_profit))
    snapshots.append({
        "label": "Base Case",
        "annual_profit": base_profit,
        "profit_impact": "positive",
        "profit_difference": 0,
        "risk_level": "Low",
    })
    return snapshots


def _fallback_kpis(farm: dict) -> List[dict]:
    """Demo-style KPIs before the first analysis run."""
    visibility = farm.get("kpi_visibility") or {}
    revenue = calculate_revenue(farm)
    costs = calculate_costs(farm)
    profit = calculate_profit(revenue, costs)
    monthly = profit / 12
    monthly_cf = calculate_monthly_cashflow(revenue, costs)
    feed_ratio = (farm.get("feed", 0) / revenue * 100) if revenue else 31
    alerts = generate_alerts(farm, profit, revenue, costs, monthly_cf)
    risk = calculate_risk_level(alerts, profit / revenue if revenue else 0)
    cash = farm.get("opening_cash_balance", 10000) + monthly

    cards = [
        {"id": "cash", "title": "Cash Available", "value": f"€{cash:,.0f}", "subtitle": f"+ €{max(monthly_cf, 0):,.0f} this month", "trend": "up"},
        {"id": "profit", "title": "Expected Monthly Profit", "value": f"€{monthly:,.0f}", "subtitle": f"Annual €{profit:,.0f}", "trend": "up"},
        {"id": "risk", "title": "Risk Level", "value": risk, "subtitle": "Stable" if risk == "Low" else "Monitor", "trend": "neutral"},
        {"id": "feed", "title": "Feed Cost %", "value": f"{feed_ratio:.0f}%", "subtitle": "Good" if feed_ratio < 35 else "High", "trend": "neutral"},
    ]
    if visibility.get("milk_price", False):
        cards.insert(1, {"id": "milk_price", "title": "Milk Price", "value": f"€{farm.get('milk_price', 0.42):.2f} / L", "subtitle": "Dairy sector", "trend": "neutral"})
    return cards


def run_farmer_analysis(
    farm_id: str | None = None,
    save_result: bool = True,
    sectors: list[str] | str | None = None,
) -> dict:
    """Run forecast and return executive dashboard payload for selected sectors."""
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    filtered_raw = get_selected_sector_data(farm_file, selected)
    farm = load_farm_for_analysis(farm_file, selected)
    profile = get_farmer_profile(farm_id, selected)

    outputs = ForecastOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        kpis=True,
    )

    forecast = run_forecast(
        farm_file=farm_file,
        outputs=outputs,
        save_result=save_result,
        generate_charts=False,
        sectors=selected,
    )

    executive = build_executive_dashboard(
        farm_file, selected, profile, forecast, farm, filtered_raw,
    )

    return {
        "success": True,
        "generated_at": forecast.get("generated_at"),
        "profile": profile,
        "selected_sectors": selected,
        **executive,
        # Legacy alias for preview KPI row during load
        "kpis": executive["executive_kpis"],
    }


def get_farmer_dashboard_preview(
    farm_id: str | None = None,
    sectors: list[str] | str | None = None,
) -> dict:
    """Dashboard shell with profile and executive KPI placeholders."""
    from models.multi_sector_farm import SECTOR_LABELS

    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    filtered_raw = get_selected_sector_data(farm_file, selected)
    farm = load_farm_for_analysis(farm_file, selected)
    profile = get_farmer_profile(farm_id, selected)
    sector_payload = get_sectors_list(farm_id, selected)
    executive_kpis = calculate_preview_kpis(farm, filtered_raw)
    return {
        "success": True,
        "profile": profile,
        "kpis": executive_kpis,
        "executive_kpis": executive_kpis,
        "overview_header": {
            "farm_name": profile.get("farm_name"),
            "selected_sectors": selected,
            "sector_labels": [SECTOR_LABELS.get(s, s.title()) for s in selected],
            "status_label": "Loading…",
            "last_updated": profile.get("last_updated"),
        },
        "has_analysis": False,
        "available_sectors": sector_payload["available_sectors"],
        "selected_sectors": selected,
    }


def get_farmer_historical_data(
    farm_id: str | None = None,
    sectors: list[str] | str | None = None,
) -> dict:
    """Historical monthly data for the Historical Data page."""
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    return get_historical_data(farm_file, selected)


def run_advanced_forecast(
    farm_id: str | None = None,
    sectors: list[str] | str | None = None,
) -> dict:
    """Advanced forecast with scenarios, Monte Carlo, and farmer interpretation."""
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    farm = load_farm_for_analysis(farm_file, selected)
    profile = get_farmer_profile(farm_id, selected)

    outputs = ForecastOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        top_risk_drivers=True,
        profitability_dashboard=True,
        advisory_summary=True,
        kpis=True,
        scenarios=False,
    )

    forecast = run_forecast(
        farm_file=farm_file,
        outputs=outputs,
        save_result=True,
        generate_charts=True,
        chart_types=["running_balance", "revenue_vs_costs", "cost_breakdown"],
        sectors=selected,
    )

    summary = forecast.get("forecast_summary") or {}
    monthly = forecast.get("monthly_forecast") or []
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
        "selected_sectors": selected,
        "kpi_visibility": forecast.get("kpi_visibility") or farm.get("kpi_visibility"),
    }


def run_monte_carlo_for_farm(
    farm_id: str | None = None,
    iterations: int = 1000,
    sectors: list[str] | str | None = None,
) -> dict:
    """Run Monte Carlo simulation for the selected farm."""
    farm_file = resolve_farm_file(farm_id)
    selected = resolve_sectors(sectors, farm_id)
    farm = load_farm_for_analysis(farm_file, selected)
    profile = get_farmer_profile(farm_id, selected)
    monte = run_monte_carlo(farm, iterations=iterations)
    return {
        "success": True,
        "farm_file": farm_file,
        "profile": profile,
        "monte_carlo": monte,
        "scenarios": calculate_scenarios(farm),
        "selected_sectors": selected,
    }
