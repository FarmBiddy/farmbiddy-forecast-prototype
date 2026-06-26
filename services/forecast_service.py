"""
Forecast Service — reusable forecast orchestration for CLI and API.

All business logic stays here; the API layer only validates input and
calls these functions.
"""

import copy
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config.paths import DATASETS_DIR, HISTORY_DIR
from forecast_engine.alerts import generate_alerts
from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.costs import calculate_costs
from forecast_engine.kpis import (
    calculate_cost_ratio,
    calculate_feed_cost_ratio,
    calculate_profit_per_cow,
    calculate_revenue_per_cow,
)
from forecast_engine.output_service import save_forecast_result
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from forecast_engine.risk_drivers import calculate_risk_drivers
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.scenarios import calculate_scenarios
from services.advisory_summary_service import generate_advisory_summary
from services.chart_service import generate_selected_charts
from services.comparison_service import COMPARISON_FIELDS, build_comparison_row
from services.dashboard_service import generate_profitability_dashboard


class FarmFileNotFoundError(FileNotFoundError):
    """Raised when a farm JSON file cannot be found."""


class ForecastFileNotFoundError(FileNotFoundError):
    """Raised when a historical forecast file cannot be found."""


class InvalidFarmDataError(ValueError):
    """Raised when farm JSON is invalid or missing required fields."""


def _farm_path(farm_file: str) -> str:
    return os.path.join(DATASETS_DIR, farm_file)


def _history_path(forecast_file: str) -> str:
    return os.path.join(HISTORY_DIR, forecast_file)


def load_farm(farm_file: str) -> dict:
    """Load and validate a farm JSON file from datasets/."""
    path = _farm_path(farm_file)

    if not os.path.exists(path):
        raise FarmFileNotFoundError(f"Farm file not found: {farm_file}")

    try:
        with open(path, "r") as file:
            farm = json.load(file)
    except json.JSONDecodeError as error:
        raise InvalidFarmDataError(f"Invalid JSON in farm file: {farm_file}") from error

    if not isinstance(farm, dict) or "farm_name" not in farm:
        raise InvalidFarmDataError(f"Farm file is missing required fields: {farm_file}")

    return farm


def save_farm(farm_file: str, farm: dict) -> None:
    """Persist a farm dict to datasets/."""
    path = _farm_path(farm_file)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(farm, file, indent=4)


def load_forecast_file(forecast_file: str) -> dict:
    """Load a saved forecast JSON file from outputs/history/."""
    path = _history_path(forecast_file)

    if not os.path.exists(path):
        raise ForecastFileNotFoundError(f"Forecast file not found: {forecast_file}")

    try:
        with open(path, "r") as file:
            forecast = json.load(file)
    except json.JSONDecodeError as error:
        raise InvalidFarmDataError(
            f"Invalid JSON in forecast file: {forecast_file}"
        ) from error

    forecast["_source_file"] = forecast_file
    return forecast


def list_available_farms() -> List[dict]:
    """Return metadata for every JSON farm file in datasets/."""
    if not os.path.exists(DATASETS_DIR):
        return []

    farms = []

    for filename in sorted(os.listdir(DATASETS_DIR)):
        if not filename.endswith(".json"):
            continue

        try:
            farm = load_farm(filename)
        except (FarmFileNotFoundError, InvalidFarmDataError):
            continue

        farms.append({
            "farm_file": filename,
            "farm_name": farm.get("farm_name", filename),
            "milking_cows": farm.get("milking_cows"),
            "milk_price": farm.get("milk_price"),
        })

    return farms


def _outputs_need_monthly_forecast(outputs) -> bool:
    fields = (
        "monthly_forecast",
        "profitability_dashboard",
        "advisory_summary",
        "top_risk_drivers",
    )
    return any(getattr(outputs, field, False) for field in fields)


def _outputs_need_alerts(outputs) -> bool:
    fields = ("alerts", "risk_level", "top_risk_drivers", "advisory_summary")
    return any(getattr(outputs, field, False) for field in fields)


def _build_full_forecast_result(farm: dict, outputs) -> dict:
    """
    Run the forecast engine and build the full internal result object.

    Expensive sections are skipped when not needed by the requested outputs.
    """
    milk_revenue = calculate_revenue(farm)
    total_costs = calculate_costs(farm)
    profit = calculate_profit(milk_revenue, total_costs)
    profit_margin = profit / milk_revenue if milk_revenue > 0 else 0

    feed_cost_ratio = calculate_feed_cost_ratio(farm, milk_revenue)
    cost_ratio = calculate_cost_ratio(total_costs, milk_revenue)
    revenue_per_cow = calculate_revenue_per_cow(farm, milk_revenue)
    profit_per_cow = calculate_profit_per_cow(farm, profit)
    monthly_cashflow = calculate_monthly_cashflow(milk_revenue, total_costs)

    forecast_result = {
        "generated_at": datetime.now().isoformat(),
        "farm_name": farm["farm_name"],
        "annual_revenue": round(milk_revenue, 2),
        "annual_costs": round(total_costs, 2),
        "annual_profit": round(profit, 2),
        "profit_margin": round(profit_margin * 100, 2),
        "feed_cost_ratio": round(feed_cost_ratio * 100, 2),
        "cost_ratio": round(cost_ratio * 100, 2),
        "revenue_per_cow": round(revenue_per_cow, 2),
        "profit_per_cow": round(profit_per_cow, 2),
        "monthly_cashflow": round(monthly_cashflow, 2),
    }

    if _outputs_need_alerts(outputs) or _outputs_need_monthly_forecast(outputs):
        alerts = generate_alerts(
            farm,
            profit,
            milk_revenue,
            total_costs,
            monthly_cashflow,
        )
        forecast_result["alerts"] = alerts
        forecast_result["risk_level"] = calculate_risk_level(alerts, profit_margin)
    elif getattr(outputs, "risk_level", False):
        alerts = generate_alerts(
            farm,
            profit,
            milk_revenue,
            total_costs,
            monthly_cashflow,
        )
        forecast_result["alerts"] = alerts
        forecast_result["risk_level"] = calculate_risk_level(alerts, profit_margin)

    if _outputs_need_monthly_forecast(outputs):
        forecast_result["monthly_forecast"] = generate_monthly_forecast(
            farm,
            milk_revenue,
            total_costs,
            farm.get("opening_cash_balance", 0),
        )

    if getattr(outputs, "scenarios", False):
        forecast_result["scenarios"] = calculate_scenarios(farm)

    if getattr(outputs, "top_risk_drivers", False):
        if "alerts" not in forecast_result:
            forecast_result["alerts"] = generate_alerts(
                farm, profit, milk_revenue, total_costs, monthly_cashflow
            )
        if "risk_level" not in forecast_result:
            forecast_result["risk_level"] = calculate_risk_level(
                forecast_result["alerts"], profit_margin
            )
        if "monthly_forecast" not in forecast_result:
            forecast_result["monthly_forecast"] = generate_monthly_forecast(
                farm,
                milk_revenue,
                total_costs,
                farm.get("opening_cash_balance", 0),
            )
        forecast_result["top_risk_drivers"] = calculate_risk_drivers(
            farm, forecast_result
        )

    if getattr(outputs, "profitability_dashboard", False):
        if "monthly_forecast" not in forecast_result:
            forecast_result["monthly_forecast"] = generate_monthly_forecast(
                farm,
                milk_revenue,
                total_costs,
                farm.get("opening_cash_balance", 0),
            )
        forecast_result["profitability_dashboard"] = generate_profitability_dashboard(
            forecast_result, farm
        )

    if getattr(outputs, "advisory_summary", False):
        if "monthly_forecast" not in forecast_result:
            forecast_result["monthly_forecast"] = generate_monthly_forecast(
                farm,
                milk_revenue,
                total_costs,
                farm.get("opening_cash_balance", 0),
            )
        if "alerts" not in forecast_result:
            forecast_result["alerts"] = generate_alerts(
                farm, profit, milk_revenue, total_costs, monthly_cashflow
            )
        if "risk_level" not in forecast_result:
            forecast_result["risk_level"] = calculate_risk_level(
                forecast_result["alerts"], profit_margin
            )
        forecast_result["advisory_summary"] = generate_advisory_summary(
            forecast_result, farm
        )

    return forecast_result


def _build_full_forecast_for_save(farm: dict) -> dict:
    """Build a complete forecast result for persistence (all sections)."""
    from models.api_models import ForecastOutputs

    all_outputs = ForecastOutputs(
        forecast_summary=True,
        monthly_forecast=True,
        alerts=True,
        risk_level=True,
        top_risk_drivers=True,
        profitability_dashboard=True,
        advisory_summary=True,
        kpis=True,
        scenarios=True,
        comparison_metrics=True,
    )
    result = _build_full_forecast_result(farm, all_outputs)
    result["top_risk_drivers"] = calculate_risk_drivers(farm, result)
    result["profitability_dashboard"] = generate_profitability_dashboard(result, farm)
    result["advisory_summary"] = generate_advisory_summary(result, farm)
    result["scenarios"] = calculate_scenarios(farm)
    return result


def _filter_response(full_result: dict, farm_file: str, outputs) -> dict:
    """Return only the forecast sections requested by the caller."""
    response = {
        "farm_file": farm_file,
        "generated_at": full_result["generated_at"],
    }

    if outputs.forecast_summary:
        response["forecast_summary"] = {
            "farm_name": full_result["farm_name"],
            "generated_at": full_result["generated_at"],
            "annual_revenue": full_result["annual_revenue"],
            "annual_costs": full_result["annual_costs"],
            "annual_profit": full_result["annual_profit"],
            "profit_margin": full_result["profit_margin"],
        }

    if outputs.monthly_forecast:
        response["monthly_forecast"] = full_result.get("monthly_forecast", [])

    if outputs.alerts:
        response["alerts"] = full_result.get("alerts", [])

    if outputs.risk_level:
        response["risk_level"] = full_result.get("risk_level")

    if outputs.top_risk_drivers:
        response["top_risk_drivers"] = full_result.get("top_risk_drivers", [])

    if outputs.profitability_dashboard:
        response["profitability_dashboard"] = full_result.get(
            "profitability_dashboard"
        )

    if outputs.advisory_summary:
        response["advisory_summary"] = full_result.get("advisory_summary")

    if outputs.kpis:
        response["kpis"] = {
            "feed_cost_ratio": full_result["feed_cost_ratio"],
            "cost_ratio": full_result["cost_ratio"],
            "revenue_per_cow": full_result["revenue_per_cow"],
            "profit_per_cow": full_result["profit_per_cow"],
            "monthly_cashflow": full_result["monthly_cashflow"],
        }

    if outputs.scenarios:
        response["scenarios"] = full_result.get("scenarios", [])

    if getattr(outputs, "comparison_metrics", False):
        row = build_comparison_row(full_result)
        response["comparison_metrics"] = row

    return response


def run_forecast(
    farm_file: str,
    outputs,
    save_result: bool = True,
    generate_charts: bool = False,
    chart_types: Optional[List[str]] = None,
) -> dict:
    """
    Execute a forecast for the given farm file and return selected outputs.

    When save_result is True, the full forecast is written to outputs/history/.
    """
    if not outputs.any_selected() and not generate_charts:
        raise ValueError("At least one output section or chart must be requested.")

    farm = load_farm(farm_file)
    full_result = _build_full_forecast_result(farm, outputs)

    saved_to = None

    if save_result:
        save_payload = _build_full_forecast_for_save(farm)
        save_payload["generated_at"] = full_result["generated_at"]
        saved_to = save_forecast_result(save_payload)

    response = _filter_response(full_result, farm_file, outputs)
    response["saved_to"] = saved_to

    if generate_charts:
        charts_to_generate = chart_types or [
            "running_balance",
            "revenue_vs_costs",
            "cost_breakdown",
            "scenario_profit",
        ]
        chart_source = _build_full_forecast_for_save(farm)
        chart_source["generated_at"] = full_result["generated_at"]
        chart_list = generate_selected_charts(
            chart_source, farm, charts_to_generate
        )
        response["charts"] = {
            item["chart_type"]: item["file_path"] for item in chart_list
        }

    return response


def apply_sandbox_changes(farm: dict, changes: dict) -> Tuple[dict, dict]:
    """
    Copy the farm and apply sandbox assumption changes.

    The original farm JSON file is never modified.
    """
    sandbox_farm = copy.deepcopy(farm)
    changes_applied = {}

    allowed_fields = {
        "milk_price",
        "feed",
        "fertiliser",
        "vet",
        "contractor",
        "labour",
        "insurance",
        "loan_repayments",
        "milking_cows",
        "litres_per_cow",
        "opening_cash_balance",
        "biss",
        "acres",
        "fuel",
        "electricity",
    }

    for field, new_value in changes.items():
        if field not in allowed_fields:
            raise ValueError(f"Unsupported sandbox field: {field}")

        old_value = sandbox_farm.get(field)
        sandbox_farm[field] = new_value
        changes_applied[field] = {"from": old_value, "to": new_value}

    return sandbox_farm, changes_applied


def run_sandbox_forecast(
    farm_file: str,
    changes: dict,
    outputs,
) -> dict:
    """Run a what-if forecast without modifying the original farm file."""
    if not outputs.any_selected():
        raise ValueError("At least one sandbox output section must be requested.")

    farm = load_farm(farm_file)
    sandbox_farm, changes_applied = apply_sandbox_changes(farm, changes)
    full_result = _build_full_forecast_result(sandbox_farm, outputs)

    response = _filter_response(full_result, farm_file, outputs)
    response["changes_applied"] = changes_applied
    return response


def run_chart_generation(farm_file: str, chart_types: List[str]) -> dict:
    """Run a full forecast and generate only the requested chart types."""
    farm = load_farm(farm_file)
    full_result = _build_full_forecast_for_save(farm)
    generated = generate_selected_charts(full_result, farm, chart_types)

    return {
        "farm_file": farm_file,
        "generated_charts": generated,
    }


# Metrics shown when comparing two or more farms in the visual interface.
LIVE_COMPARISON_METRICS = [
    "annual_profit",
    "profit_margin",
    "risk_level",
    "revenue_per_cow",
    "profit_per_cow",
    "feed_cost_ratio",
]


def _analyse_outputs_to_forecast(outputs) -> "ForecastOutputs":
    """Convert visual-interface output toggles to forecast engine options."""
    from models.api_models import ForecastOutputs

    return ForecastOutputs(
        forecast_summary=outputs.forecast_summary,
        monthly_forecast=outputs.monthly_forecast,
        alerts=outputs.alerts,
        risk_level=outputs.risk_level,
        top_risk_drivers=outputs.top_risk_drivers,
        profitability_dashboard=outputs.profitability_dashboard,
        advisory_summary=outputs.advisory_summary,
        kpis=outputs.kpis,
        scenarios=outputs.scenarios,
    )


def _result_to_comparison_row(result: dict) -> dict:
    """Build one comparison row from a filtered forecast response."""
    summary = result.get("forecast_summary") or {}
    kpis = result.get("kpis") or {}

    return {
        "farm_name": summary.get("farm_name"),
        "farm_file": result.get("farm_file"),
        "annual_profit": summary.get("annual_profit"),
        "profit_margin": summary.get("profit_margin"),
        "risk_level": result.get("risk_level"),
        "revenue_per_cow": kpis.get("revenue_per_cow"),
        "profit_per_cow": kpis.get("profit_per_cow"),
        "feed_cost_ratio": kpis.get("feed_cost_ratio"),
    }


def run_multi_farm_analysis(
    farm_files: List[str],
    outputs,
    chart_types: Optional[List[str]] = None,
    save_result: bool = True,
) -> dict:
    """
    Run forecasts for one or more farms for the visual web interface.

    Returns a single-farm dashboard payload or a multi-farm comparison.
    """
    multi_farm = len(farm_files) >= 2

    # Comparison mode needs summary KPIs even if the user forgot to tick them.
    if multi_farm:
        outputs.forecast_summary = True
        outputs.kpis = True
        if outputs.forecast_comparison:
            outputs.risk_level = True

    forecast_outputs = _analyse_outputs_to_forecast(outputs)

    if not forecast_outputs.any_selected() and not outputs.charts:
        forecast_outputs.forecast_summary = True
        forecast_outputs.kpis = True

    results = []

    for farm_file in farm_files:
        result = run_forecast(
            farm_file=farm_file,
            outputs=forecast_outputs,
            save_result=save_result,
            generate_charts=outputs.charts,
            chart_types=chart_types,
        )
        results.append(result)

    if multi_farm:
        comparison = [_result_to_comparison_row(item) for item in results]
        comparison.sort(key=lambda row: row.get("annual_profit") or 0, reverse=True)

        return {
            "mode": "comparison",
            "results": results,
            "comparison": comparison,
            "comparison_metrics": LIVE_COMPARISON_METRICS,
        }

    return {
        "mode": "single",
        "results": results,
        "comparison": None,
        "comparison_metrics": None,
    }
