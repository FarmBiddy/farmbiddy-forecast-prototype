def print_forecast_summary(
    farm,
    revenue,
    costs,
    profit,
    alerts,
    feed_cost_ratio,
    cost_ratio,
    revenue_per_cow,
    profit_per_cow,
    risk_level,
):
    margin = (profit / revenue * 100) if revenue > 0 else 0

    print("\nFORECAST SUMMARY")
    print("Farm:", farm["farm_name"])
    print("Annual Revenue: €", round(revenue, 2))
    print("Annual Costs: €", round(costs, 2))
    print("Annual Profit: €", round(profit, 2))
    print("Margin %:", round(margin, 2))
    print("Risk Level:", risk_level)

    print("\nAlerts:")
    if alerts:
        for alert in alerts:
            print("-", alert)
    else:
        print("- No major alerts.")

    print("\nFeed Cost Ratio:", feed_cost_ratio, "%")
    print("Cost Ratio:", cost_ratio, "%")
    print("Revenue Per Cow: €", revenue_per_cow)
    print("Profit Per Cow: €", profit_per_cow)
