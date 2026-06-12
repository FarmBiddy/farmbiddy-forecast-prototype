def calculate_monthly_cashflow(revenue, costs):
    """
    Calculates the average monthly cashflow.
    """
    return (revenue - costs) / 12


def generate_monthly_forecast(farm, revenue, costs, opening_cash_balance):
    """
    Generates a 12-month cashflow forecast and returns it as a list of dictionaries.
    """

    milk_revenue = farm["milking_cows"] * farm["litres_per_cow"] * farm["milk_price"]

    monthly_milk_revenue = milk_revenue / 12
    monthly_costs = costs / 12
    running_balance = opening_cash_balance

    monthly_forecast = []

    for month in range(1, 13):
        monthly_revenue = monthly_milk_revenue

        if month == farm["scheme_payment_months"]["biss"]:
            monthly_revenue += farm["biss"]

        if month == farm["scheme_payment_months"]["acres"]:
            monthly_revenue += farm["acres"]

        cashflow = monthly_revenue - monthly_costs
        running_balance += cashflow

        monthly_forecast.append({
            "month": month,
            "revenue": round(monthly_revenue, 2),
            "costs": round(monthly_costs, 2),
            "cashflow": round(cashflow, 2),
            "running_balance": round(running_balance, 2)
        })

    return monthly_forecast