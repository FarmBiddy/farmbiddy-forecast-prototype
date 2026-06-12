"""
Forecast Comparison — compare historical forecast outputs side by side.

Loads saved JSON forecasts from outputs/history and presents a ranked
table so advisors can benchmark farms on profit, margin, and risk.
"""

import csv
import json
import os
from datetime import datetime

from config.paths import COMPARISONS_DIR, HISTORY_DIR, ensure_output_dirs

# Fields extracted from each saved forecast for comparison.
COMPARISON_FIELDS = [
    "farm_name",
    "generated_at",
    "annual_revenue",
    "annual_costs",
    "annual_profit",
    "profit_margin",
    "risk_level",
    "revenue_per_cow",
    "profit_per_cow",
    "feed_cost_ratio",
]

# Metrics allowed in selective comparison requests.
ALLOWED_METRICS = [
    field
    for field in COMPARISON_FIELDS
    if field not in ("farm_name", "generated_at")
]

RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def build_comparison_row(forecast: dict, source_file: str = None) -> dict:
    """Extract comparison metrics from a single forecast result."""
    row = {field: forecast.get(field) for field in COMPARISON_FIELDS}

    if source_file:
        row["source_file"] = source_file
    elif forecast.get("_source_file"):
        row["source_file"] = forecast["_source_file"]

    return row


def load_forecast_outputs(folder_path=HISTORY_DIR):
    """
    Load all JSON forecast files from the history folder.

    Returns an empty list if the folder does not exist or contains
    no valid forecast JSON files.
    """
    if not os.path.exists(folder_path):
        return []

    forecasts = []

    for filename in os.listdir(folder_path):
        # Skip anything that is not a JSON forecast file.
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(folder_path, filename)

        try:
            with open(filepath, "r") as file:
                forecast = json.load(file)
                forecast["_source_file"] = filename
                forecasts.append(forecast)
        except (json.JSONDecodeError, OSError):
            # Skip files that cannot be read or parsed.
            continue

    return forecasts


def load_forecasts_by_filenames(
    forecast_files: list,
    folder_path=HISTORY_DIR,
) -> list:
    """
    Load specific forecast JSON files by filename.

    Raises FileNotFoundError if any requested file is missing.
    """
    if not forecast_files:
        raise ValueError("At least one forecast file must be provided.")

    forecasts = []

    for filename in forecast_files:
        filepath = os.path.join(folder_path, filename)

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Forecast file not found: {filename}")

        try:
            with open(filepath, "r") as file:
                forecast = json.load(file)
                forecast["_source_file"] = filename
                forecasts.append(forecast)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON in forecast file: {filename}") from error

    return forecasts


def _validate_metrics(metrics: list) -> list:
    """Ensure requested comparison metrics are supported."""
    if not metrics:
        return ALLOWED_METRICS.copy()

    invalid = [metric for metric in metrics if metric not in ALLOWED_METRICS]

    if invalid:
        raise ValueError(
            f"Invalid comparison metrics: {', '.join(invalid)}. "
            f"Allowed: {', '.join(ALLOWED_METRICS)}"
        )

    return metrics


def generate_selective_comparison(forecasts: list, metrics: list = None) -> dict:
    """
    Build a comparison using only the requested metrics.

    Always includes farm_name, generated_at, and source_file for context.
    Sorted by annual_profit (highest first) when that metric is present.
    """
    selected_metrics = _validate_metrics(metrics or [])
    comparison = []

    for forecast in forecasts:
        row = {
            "farm_name": forecast.get("farm_name"),
            "generated_at": forecast.get("generated_at"),
            "source_file": forecast.get("_source_file"),
        }

        for metric in selected_metrics:
            row[metric] = forecast.get(metric)

        comparison.append(row)

    if "annual_profit" in selected_metrics or not metrics:
        comparison.sort(
            key=lambda row: row.get("annual_profit") or 0,
            reverse=True,
        )

    return {
        "comparison": comparison,
        "metrics": selected_metrics,
        "count": len(comparison),
    }


def generate_forecast_comparison(forecasts):
    """
    Build a comparison list from loaded forecast results.

    Returns one summary dictionary per forecast, sorted by annual_profit
    from highest to lowest.
    """
    comparison = []

    for forecast in forecasts:
        row = build_comparison_row(forecast)
        comparison.append(row)

    # Highest profit first — easiest way to spot the strongest farm.
    comparison.sort(
        key=lambda row: row.get("annual_profit") or 0,
        reverse=True,
    )

    return comparison


def _display_farm_name(farm_name):
    """Shorten farm names for the comparison table (e.g. drop ' Dairy')."""
    if farm_name and farm_name.endswith(" Dairy"):
        return farm_name[:-6]
    return farm_name or "Unknown"


def print_forecast_comparison(comparison):
    """Print a clean side-by-side comparison table for advisors."""
    print("--------------------------------")
    print("FORECAST COMPARISON")
    print("--------------------------------")

    if not comparison:
        print("No forecast outputs found to compare.")
        print("--------------------------------")
        return

    # Column widths keep the table aligned in the terminal.
    farm_width = 18
    profit_width = 12
    margin_width = 11
    risk_width = 10
    profit_cow_width = 12

    header = (
        f"{'Farm':<{farm_width}}"
        f"{'Profit':>{profit_width}}"
        f"{'Margin':>{margin_width}}"
        f"{'Risk':>{risk_width}}"
        f"{'Profit/Cow':>{profit_cow_width}}"
    )
    print(header)

    for row in comparison:
        farm = _display_farm_name(row.get("farm_name"))
        profit = row.get("annual_profit") or 0
        margin = row.get("profit_margin") or 0
        risk = row.get("risk_level") or "N/A"
        profit_per_cow = row.get("profit_per_cow") or 0

        line = (
            f"{farm:<{farm_width}}"
            f"{f'€{profit:,.0f}':>{profit_width}}"
            f"{f'{margin:.1f}%':>{margin_width}}"
            f"{risk:>{risk_width}}"
            f"{f'€{profit_per_cow:,.0f}':>{profit_cow_width}}"
        )
        print(line)

    print("--------------------------------")


def save_forecast_comparison(comparison):
    """
    Save the comparison as JSON and CSV files.

    Returns a dictionary with the saved file paths.
    """
    ensure_output_dirs()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"forecast_comparison_{timestamp}"

    json_path = os.path.join(COMPARISONS_DIR, f"{base_name}.json")
    csv_path = os.path.join(COMPARISONS_DIR, f"{base_name}.csv")

    with open(json_path, "w") as file:
        json.dump(comparison, file, indent=4)

    # CSV gives advisors a spreadsheet-friendly export.
    with open(csv_path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COMPARISON_FIELDS)
        writer.writeheader()
        writer.writerows(comparison)

    return {
        "json_path": json_path,
        "csv_path": csv_path,
    }


def list_forecast_history(folder_path=HISTORY_DIR, sort_by: str = "generated_at") -> dict:
    """
    Return a summary list of saved forecasts for the history endpoint.

    Supports sorting by annual_profit, generated_at, or risk_level.
    """
    allowed_sorts = {"annual_profit", "generated_at", "risk_level"}

    if sort_by not in allowed_sorts:
        raise ValueError(
            f"Invalid sort_by value: {sort_by}. "
            f"Allowed: {', '.join(sorted(allowed_sorts))}"
        )

    forecasts = load_forecast_outputs(folder_path)
    history = []

    for forecast in forecasts:
        history.append({
            "forecast_file": forecast.get("_source_file"),
            "farm_name": forecast.get("farm_name"),
            "generated_at": forecast.get("generated_at"),
            "annual_profit": forecast.get("annual_profit"),
            "risk_level": forecast.get("risk_level"),
        })

    if sort_by == "annual_profit":
        history.sort(key=lambda row: row.get("annual_profit") or 0, reverse=True)
    elif sort_by == "generated_at":
        history.sort(key=lambda row: row.get("generated_at") or "", reverse=True)
    elif sort_by == "risk_level":
        history.sort(
            key=lambda row: RISK_ORDER.get(row.get("risk_level"), 99)
        )

    return {
        "forecasts": history,
        "count": len(history),
        "sort_by": sort_by,
    }


def _best_row(rows: list, metric: str, highest: bool = True) -> dict:
    """Find the best or worst row for a numeric metric."""
    numeric_rows = [
        row for row in rows if row.get(metric) is not None
    ]

    if not numeric_rows:
        return None

    selected = (
        max if highest else min
    )(numeric_rows, key=lambda row: row.get(metric))

    return {
        "farm_name": selected.get("farm_name"),
        "source_file": selected.get("source_file"),
        "value": selected.get(metric),
    }


def generate_benchmark(forecasts: list) -> dict:
    """
    Calculate benchmarking highlights across selected forecasts.

    Identifies best/worst margins, highest per-cow performance,
    lowest feed pressure, and highest risk farm.
    """
    rows = [build_comparison_row(forecast) for forecast in forecasts]

    if not rows:
        return {}

    highest_risk = min(
        rows,
        key=lambda row: RISK_ORDER.get(row.get("risk_level"), 99),
    )

    return {
        "best_profit_margin": _best_row(rows, "profit_margin", highest=True),
        "worst_profit_margin": _best_row(rows, "profit_margin", highest=False),
        "highest_revenue_per_cow": _best_row(rows, "revenue_per_cow", highest=True),
        "highest_profit_per_cow": _best_row(rows, "profit_per_cow", highest=True),
        "lowest_feed_cost_ratio": _best_row(rows, "feed_cost_ratio", highest=False),
        "highest_risk_farm": {
            "farm_name": highest_risk.get("farm_name"),
            "source_file": highest_risk.get("source_file"),
            "value": highest_risk.get("risk_level"),
        },
    }


def compare_forecasts(
    forecast_files: list = None,
    compare_all: bool = False,
    metrics: list = None,
    folder_path=HISTORY_DIR,
) -> dict:
    """
    Load and compare forecasts by file list or all history files.
    """
    if compare_all:
        forecasts = load_forecast_outputs(folder_path)
    elif forecast_files:
        forecasts = load_forecasts_by_filenames(forecast_files, folder_path)
    else:
        raise ValueError(
            "Provide forecast_files or set compare_all to true."
        )

    if not forecasts:
        raise ValueError("No forecast files found to compare.")

    return generate_selective_comparison(forecasts, metrics)


def benchmark_forecasts(
    forecast_files: list = None,
    compare_all: bool = False,
    folder_path=HISTORY_DIR,
) -> dict:
    """Load forecasts and return benchmarking summary."""
    if compare_all:
        forecasts = load_forecast_outputs(folder_path)
    elif forecast_files:
        forecasts = load_forecasts_by_filenames(forecast_files, folder_path)
    else:
        raise ValueError(
            "Provide forecast_files or set compare_all to true."
        )

    if not forecasts:
        raise ValueError("No forecast files found to benchmark.")

    return generate_benchmark(forecasts)
