import os
from datetime import datetime

import plotly.graph_objects as go

from config.paths import CHARTS_DIR, ensure_output_dirs

VALID_CHART_TYPES = [
    "running_balance",
    "revenue_vs_costs",
    "cost_breakdown",
    "scenario_profit",
    "kpi_comparison",
    "historical_profit_trend",
]

COST_FIELDS = [
    ("feed", "Feed"),
    ("fertiliser", "Fertiliser"),
    ("vet", "Vet"),
    ("contractor", "Contractor"),
    ("labour", "Labour"),
    ("insurance", "Insurance"),
    ("loan_repayments", "Loan Repayments"),
]


def _safe_farm_name(farm_name):
    return farm_name.lower().replace(" ", "_")


def _chart_timestamp(forecast_result):
    generated_at = forecast_result.get("generated_at")

    if generated_at:
        timestamp = datetime.fromisoformat(generated_at)
        return timestamp.strftime("%Y%m%d_%H%M%S")

    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_chart_path(forecast_result, chart_type):
    ensure_output_dirs()

    farm_name = _safe_farm_name(forecast_result["farm_name"])
    timestamp = _chart_timestamp(forecast_result)

    return os.path.join(CHARTS_DIR, f"{farm_name}_{chart_type}_{timestamp}.html")


def _save_chart(fig, output_path):
    fig.write_html(output_path)
    return output_path


def save_running_balance_chart(forecast_result):
    monthly_forecast = forecast_result["monthly_forecast"]

    months = [f"Month {row['month']}" for row in monthly_forecast]
    balances = [row["running_balance"] for row in monthly_forecast]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=months,
            y=balances,
            mode="lines+markers",
            name="Running Balance",
            line={"color": "#2E86AB", "width": 3},
        )
    )

    fig.update_layout(
        title=f"{forecast_result['farm_name']} - Monthly Running Balance",
        xaxis_title="Month",
        yaxis_title="Balance (€)",
        template="plotly_white",
    )

    output_path = _build_chart_path(forecast_result, "running_balance")
    return _save_chart(fig, output_path)


def save_revenue_vs_costs_chart(forecast_result):
    monthly_forecast = forecast_result["monthly_forecast"]

    months = [f"Month {row['month']}" for row in monthly_forecast]
    revenues = [row["revenue"] for row in monthly_forecast]
    costs = [row["costs"] for row in monthly_forecast]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=months,
            y=revenues,
            mode="lines+markers",
            name="Revenue",
            line={"color": "#28A745", "width": 3},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=months,
            y=costs,
            mode="lines+markers",
            name="Costs",
            line={"color": "#DC3545", "width": 3},
        )
    )

    fig.update_layout(
        title=f"{forecast_result['farm_name']} - Monthly Revenue vs Costs",
        xaxis_title="Month",
        yaxis_title="Amount (€)",
        template="plotly_white",
    )

    output_path = _build_chart_path(forecast_result, "revenue_vs_costs")
    return _save_chart(fig, output_path)


def save_cost_breakdown_chart(forecast_result, farm):
    labels = []
    values = []

    for field_name, label in COST_FIELDS:
        labels.append(label)
        values.append(farm[field_name])

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color="#6C757D",
            )
        ]
    )

    fig.update_layout(
        title=f"{forecast_result['farm_name']} - Annual Cost Breakdown",
        xaxis_title="Cost Category",
        yaxis_title="Amount (€)",
        template="plotly_white",
    )

    output_path = _build_chart_path(forecast_result, "cost_breakdown")
    return _save_chart(fig, output_path)


def save_scenario_profit_chart(forecast_result):
    scenarios = forecast_result.get("scenarios")

    if not scenarios:
        return None

    names = [scenario["name"] for scenario in scenarios]
    profits = [scenario["profit"] for scenario in scenarios]
    colors = ["#28A745", "#2E86AB", "#DC3545"]

    fig = go.Figure(
        data=[
            go.Bar(
                x=names,
                y=profits,
                marker_color=colors[: len(names)],
            )
        ]
    )

    fig.update_layout(
        title=f"{forecast_result['farm_name']} - Scenario Profit Comparison",
        xaxis_title="Scenario",
        yaxis_title="Profit (€)",
        template="plotly_white",
    )

    output_path = _build_chart_path(forecast_result, "scenario_profit")
    return _save_chart(fig, output_path)


def save_kpi_comparison_chart(comparison_rows, metrics=None):
    """
    Grouped bar chart comparing farms across selected KPI metrics.

    Expects rows from comparison_service with farm_name and metric values.
    """
    if not comparison_rows:
        return None

    selected_metrics = metrics or [
        "annual_profit",
        "profit_margin",
        "profit_per_cow",
        "feed_cost_ratio",
    ]

    farm_labels = []
    for row in comparison_rows:
        name = row.get("farm_name", "Unknown")
        if name.endswith(" Dairy"):
            name = name[:-6]
        farm_labels.append(name)

    fig = go.Figure()

    colors = ["#2E86AB", "#28A745", "#F4A261", "#DC3545", "#6C757D"]

    for index, metric in enumerate(selected_metrics):
        values = [row.get(metric, 0) for row in comparison_rows]
        label = metric.replace("_", " ").title()

        fig.add_trace(
            go.Bar(
                name=label,
                x=farm_labels,
                y=values,
                marker_color=colors[index % len(colors)],
            )
        )

    fig.update_layout(
        title="Farm KPI Comparison",
        xaxis_title="Farm",
        yaxis_title="Value",
        barmode="group",
        template="plotly_white",
    )

    os.makedirs(CHARTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(CHARTS_DIR, f"kpi_comparison_{timestamp}.html")
    return _save_chart(fig, output_path)


def save_historical_profit_trend_chart(history_rows, farm_name):
    """
    Line chart showing how annual profit changes across historical runs.
    """
    if not history_rows:
        return None

    sorted_rows = sorted(
        history_rows,
        key=lambda row: row.get("generated_at") or "",
    )

    dates = [row.get("generated_at", "")[:10] for row in sorted_rows]
    profits = [row.get("annual_profit", 0) for row in sorted_rows]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=profits,
            mode="lines+markers",
            name="Annual Profit",
            line={"color": "#2E86AB", "width": 3},
        )
    )

    fig.update_layout(
        title=f"{farm_name} - Historical Profit Trend",
        xaxis_title="Forecast Date",
        yaxis_title="Annual Profit (€)",
        template="plotly_white",
    )

    os.makedirs(CHARTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _safe_farm_name(farm_name)
    output_path = os.path.join(
        CHARTS_DIR,
        f"{safe_name}_historical_profit_trend_{timestamp}.html",
    )
    return _save_chart(fig, output_path)


def _chart_result(chart_type: str, file_path: str) -> dict:
    """Standard chart generation response object."""
    return {
        "chart_type": chart_type,
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
    }


def generate_selected_charts(forecast_result, farm, chart_types):
    """
    Generate only the requested chart types for a forecast.

    Returns a list of generated chart metadata dictionaries.
    """
    from services.comparison_service import (
        build_comparison_row,
        load_forecast_outputs,
    )

    invalid = [chart for chart in chart_types if chart not in VALID_CHART_TYPES]

    if invalid:
        raise ValueError(
            f"Invalid chart type(s): {', '.join(invalid)}. "
            f"Allowed: {', '.join(VALID_CHART_TYPES)}"
        )

    generated = []
    chart_map = {
        "running_balance": lambda: save_running_balance_chart(forecast_result),
        "revenue_vs_costs": lambda: save_revenue_vs_costs_chart(forecast_result),
        "cost_breakdown": lambda: save_cost_breakdown_chart(forecast_result, farm),
        "scenario_profit": lambda: save_scenario_profit_chart(forecast_result),
    }

    for chart_type in chart_types:
        if chart_type == "kpi_comparison":
            all_forecasts = load_forecast_outputs()
            comparison_rows = [build_comparison_row(item) for item in all_forecasts]

            if not comparison_rows:
                comparison_rows = [build_comparison_row(forecast_result)]

            path = save_kpi_comparison_chart(comparison_rows)
            if path:
                generated.append(_chart_result(chart_type, path))
            continue

        if chart_type == "historical_profit_trend":
            farm_name = forecast_result["farm_name"]
            all_forecasts = load_forecast_outputs()
            farm_history = [
                build_comparison_row(item)
                for item in all_forecasts
                if item.get("farm_name") == farm_name
            ]

            if not farm_history:
                farm_history = [build_comparison_row(forecast_result)]

            path = save_historical_profit_trend_chart(farm_history, farm_name)
            if path:
                generated.append(_chart_result(chart_type, path))
            continue

        path = chart_map[chart_type]()

        if path:
            generated.append(_chart_result(chart_type, path))

    return generated


def _parse_chart_filename(filename):
    """
    Extract chart metadata from a saved chart filename.

    Pattern: {farm}_{chart_type}_{timestamp}.html
    """
    if not filename.endswith(".html"):
        return None, None, None

    base = filename[:-5]
    parts = base.rsplit("_", 2)

    if len(parts) < 3:
        return None, None, None

    farm_part, chart_type, timestamp = parts[0], parts[1], parts[2]

    # Handle multi-part chart types like revenue_vs_costs
    known_types = sorted(VALID_CHART_TYPES, key=len, reverse=True)
    for chart_type_name in known_types:
        suffix = f"_{chart_type_name}_"
        if suffix in base:
            farm_part, remainder = base.split(suffix, 1)
            timestamp = remainder
            return farm_part.replace("_", " ").title(), chart_type_name, timestamp

    return farm_part.replace("_", " ").title(), chart_type, timestamp


def list_chart_files(folder_path=CHARTS_DIR):
    """Return metadata for all chart HTML files in outputs/charts/."""
    if not os.path.exists(folder_path):
        return []

    charts = []

    for filename in sorted(os.listdir(folder_path)):
        if not filename.endswith(".html"):
            continue

        file_path = os.path.join(folder_path, filename)
        farm_name, chart_type, timestamp = _parse_chart_filename(filename)

        try:
            created_at = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").isoformat()
        except (TypeError, ValueError):
            created_at = None

        charts.append({
            "file_name": filename,
            "file_path": file_path.replace("\\", "/"),
            "chart_type": chart_type,
            "farm_name": farm_name,
            "created_at": created_at,
            "size_bytes": os.path.getsize(file_path),
        })

    return charts


def get_chart_info(chart_name, folder_path=CHARTS_DIR):
    """Return metadata for a single chart file by filename."""
    file_path = os.path.join(folder_path, chart_name)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Chart not found: {chart_name}")

    farm_name, chart_type, timestamp = _parse_chart_filename(chart_name)

    try:
        created_at = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").isoformat()
    except (TypeError, ValueError):
        created_at = None

    return {
        "file_name": chart_name,
        "file_path": file_path.replace("\\", "/"),
        "chart_type": chart_type,
        "farm_name": farm_name,
        "created_at": created_at,
        "size_bytes": os.path.getsize(file_path),
    }


def save_all_charts(forecast_result, farm):
    chart_paths = {
        "running_balance": save_running_balance_chart(forecast_result),
        "revenue_vs_costs": save_revenue_vs_costs_chart(forecast_result),
        "cost_breakdown": save_cost_breakdown_chart(forecast_result, farm),
    }

    scenario_path = save_scenario_profit_chart(forecast_result)

    if scenario_path:
        chart_paths["scenario_profit"] = scenario_path

    return chart_paths
