def generate_alerts(farm, profit, revenue, costs, monthly_cashflow):
    alerts = []

    opening_balance = farm.get("opening_cash_balance", 0)
    ending_balance = opening_balance + profit
    monthly_costs = costs / 12
    min_balance = min(opening_balance, ending_balance)

    if profit < 0:
        alerts.append("Negative profit: The farm is forecasted to make a loss.")

    if revenue > 0:
        profit_margin = profit / revenue

        if profit_margin < 0.15:
            alerts.append("Low profit margin: Margin is below 15%.")

        feed_cost_pct = farm["feed"] / revenue

        if feed_cost_pct > 0.35:
            alerts.append(
                "High feed cost percentage: Feed exceeds 35% of revenue."
            )

    if monthly_cashflow < 0:
        alerts.append(
            "Negative monthly cashflow: Monthly income does not cover monthly costs."
        )

    if min_balance < monthly_costs:
        alerts.append(
            "Low cash balance: Cash balance falls below one month of operating costs."
        )

    return alerts