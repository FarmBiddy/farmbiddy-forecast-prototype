import json
import os
from datetime import datetime


def save_forecast_result(farm, revenue, costs, profit, monthly_cashflow):
    result = {
        "farm_name": farm["farm_name"],
        "generated_at": datetime.now().isoformat(),
        "annual_revenue": round(revenue, 2),
        "annual_costs": round(costs, 2),
        "annual_profit": round(profit, 2),
        "monthly_cashflow": round(monthly_cashflow, 2)
    }

    os.makedirs("outputs", exist_ok=True)

    file_name = farm["farm_name"].lower().replace(" ", "_")
    output_path = f"outputs/{file_name}_forecast.json"

    with open(output_path, "w") as file:
        json.dump(result, file, indent=4)

    print("\nForecast saved to:", output_path)