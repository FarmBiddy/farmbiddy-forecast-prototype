#IMPORTS
import json

import os

from datetime import datetime

from forecast_engine.revenue import calculate_revenue
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.scenarios import calculate_scenarios, print_scenarios
from services.chart_service import save_all_charts
from services.advisory_summary_service import (
    generate_advisory_summary,
    print_advisory_summary,
)
from services.dashboard_service import (
    generate_profitability_dashboard,
    print_profitability_dashboard,
)
from services.comparison_service import (
    load_forecast_outputs,
    generate_forecast_comparison,
    print_forecast_comparison,
    save_forecast_comparison,
)
from forecast_engine.alerts import generate_alerts
from forecast_engine.risk_level import calculate_risk_level
from forecast_engine.fc_summary import print_forecast_summary
from forecast_engine.output_service import save_forecast_result
from forecast_engine.kpis import (
    calculate_feed_cost_ratio,
    calculate_cost_ratio,
    calculate_revenue_per_cow,
    calculate_profit_per_cow
)

from models.forecast_context import ForecastContext
from forecast_engine.advisor_sandbox import run_advisor_sandbox
from forecast_engine.risk_drivers import (
    calculate_risk_drivers,
    print_top_risk_drivers,
)


files = os.listdir("datasets")

json_files = []

for file in files:
    if file.endswith(".json"):
        json_files.append(file)

print("Available farm files:")

for index, file in enumerate(json_files, start=1):
    print(index, "-", file)

choice = int(input("Choose a farm file number: "))

selected_file = json_files[choice - 1]

with open(f"datasets/{selected_file}", "r") as file:
    farm = json.load(file)

context = ForecastContext(farm)

print("Selected file:", selected_file)
print("Forecast Context Built For:", context.farm_name)

# Future refactor: calculators can receive ForecastContext instead of raw farm dictionaries.

#CALCULATIONS
milk_revenue = calculate_revenue(farm)
total_costs = calculate_costs(farm)
profit = calculate_profit(milk_revenue, total_costs)
profit_margin = profit / milk_revenue
feed_cost_ratio = calculate_feed_cost_ratio(farm, milk_revenue)
cost_ratio = calculate_cost_ratio(total_costs, milk_revenue)
revenue_per_cow = calculate_revenue_per_cow(farm, milk_revenue)
profit_per_cow = calculate_profit_per_cow(farm, profit)


monthly_cashflow = calculate_monthly_cashflow(
    milk_revenue,
    total_costs
)

alerts = generate_alerts(
    farm,
    profit,
    milk_revenue,
    total_costs,
    monthly_cashflow,
)

risk_level = calculate_risk_level(alerts, profit_margin)

#OUTPUTS   
print("Generated at:", datetime.now().isoformat())
print("Farm:", farm["farm_name"])
print("Milk Revenue: €", round(milk_revenue, 2))
print("Total Costs: €", round(total_costs, 2))
print("Profit: €", round(profit, 2))
print("Monthly Cashflow: €", round(monthly_cashflow, 2))
print_scenarios(farm)
print("\nMonthly Forecast:")

monthly_forecast = generate_monthly_forecast(
    farm,
    milk_revenue,
    total_costs,
    farm["opening_cash_balance"]
)

for month in monthly_forecast:
    print(
        "Month", month["month"],
        "| Revenue: €", month["revenue"],
        "| Costs: €", month["costs"],
        "| Cashflow: €", month["cashflow"],
        "| Running Balance: €", month["running_balance"]
    )

print("\nAlerts:")

if alerts:
    for alert in alerts:
        print("-", alert)
else:
    print("No major alerts.")

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
    "risk_level": risk_level,
    "alerts": alerts,
    "monthly_forecast": monthly_forecast,
    "scenarios": calculate_scenarios(farm),
}

risk_drivers = calculate_risk_drivers(farm, forecast_result)
forecast_result["top_risk_drivers"] = risk_drivers

profitability_dashboard = generate_profitability_dashboard(
    forecast_result, farm
)
forecast_result["profitability_dashboard"] = profitability_dashboard

advisory_summary = generate_advisory_summary(forecast_result, farm)
forecast_result["advisory_summary"] = advisory_summary

output_path = save_forecast_result(forecast_result)


print("Profit Margin:", round(profit_margin * 100, 2), "%")
print("Feed Cost Ratio:", round(feed_cost_ratio * 100, 2), "%")
print("Cost Ratio:", round(cost_ratio * 100, 2), "%")
print("Revenue Per Cow:", round(revenue_per_cow, 2))
print("Profit Per Cow:", round(profit_per_cow, 2))
print("Risk Level:", risk_level)
print("\nForecast saved to:", output_path)

chart_paths = save_all_charts(forecast_result, farm)

print("\nCharts saved:")
for chart_name, chart_path in chart_paths.items():
    print(f"- {chart_name}: {chart_path}")

print_forecast_summary(
    farm,
    forecast_result["annual_revenue"],
    forecast_result["annual_costs"],
    forecast_result["annual_profit"],
    forecast_result["alerts"],
    forecast_result["feed_cost_ratio"],
    forecast_result["cost_ratio"],
    forecast_result["revenue_per_cow"],
    forecast_result["profit_per_cow"],
    forecast_result["risk_level"],
)

print_profitability_dashboard(profitability_dashboard)

print_advisory_summary(advisory_summary)

print_top_risk_drivers(risk_drivers)

comparison_choice = input(
    "\nWould you like to compare historical forecast runs? (y/n): "
).strip().lower()

if comparison_choice == "y":
    historical_forecasts = load_forecast_outputs()

    if not historical_forecasts:
        print("\nNo historical forecast files found in outputs/history.")
    else:
        comparison = generate_forecast_comparison(historical_forecasts)
        print_forecast_comparison(comparison)

        saved_paths = save_forecast_comparison(comparison)
        print("\nComparison saved to:")
        print("- JSON:", saved_paths["json_path"])
        print("- CSV:", saved_paths["csv_path"])

sandbox_choice = input(
    "\nWould you like to enter Advisor Sandbox Mode? (y/n): "
).strip().lower()

if sandbox_choice == "y":
    run_advisor_sandbox(farm)
