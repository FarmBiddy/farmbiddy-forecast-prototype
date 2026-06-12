from forecast_engine.revenue import calculate_revenue
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit


def calculate_scenarios(farm):
    base_price = farm["milk_price"]
    costs = calculate_costs(farm)
    scenarios = [
        ("Best case (+10%)", base_price * 1.10),
        ("Base case", base_price),
        ("Worst case (-10%)", base_price * 0.90),
    ]

    results = []

    for name, milk_price in scenarios:
        revenue = calculate_revenue(farm, milk_price)
        profit = calculate_profit(revenue, costs)

        results.append({
            "name": name,
            "milk_price": round(milk_price, 2),
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
        })

    return results


def print_scenarios(farm):
    print("\nScenarios:")

    for scenario in calculate_scenarios(farm):
        print(scenario["name"])
        print("  Milk price: €", scenario["milk_price"])
        print("  Revenue: €", scenario["revenue"])
        print("  Profit: €", scenario["profit"])