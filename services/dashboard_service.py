"""
Profitability Dashboard — a one-page advisor view of key farm financial KPIs.

Reads from the existing forecast_result wherever possible so forecast
calculations are not duplicated.
"""

MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _find_lowest_cash_balance(monthly_forecast):
    """
    Return the month name and balance for the lowest running_balance
    in the monthly forecast.
    """
    lowest_month = min(
        monthly_forecast,
        key=lambda month: month["running_balance"],
    )

    month_number = lowest_month["month"]
    month_name = MONTH_NAMES[month_number]
    balance = round(lowest_month["running_balance"], 2)

    return month_name, balance


def _calculate_cost_per_cow(annual_costs, milking_cows):
    """Annual costs divided by herd size."""
    if milking_cows <= 0:
        return 0

    return round(annual_costs / milking_cows, 2)


def generate_profitability_dashboard(forecast_result, farm):
    """
    Build a profitability dashboard dictionary from forecast results.

    Uses existing forecast KPIs and only calculates cost_per_cow and
    lowest cash balance from farm / monthly_forecast data.
    """
    monthly_forecast = forecast_result["monthly_forecast"]
    lowest_month_name, lowest_balance = _find_lowest_cash_balance(
        monthly_forecast
    )

    milking_cows = farm["milking_cows"]
    annual_costs = forecast_result["annual_costs"]
    cost_per_cow = _calculate_cost_per_cow(annual_costs, milking_cows)

    return {
        "farm_name": forecast_result["farm_name"],
        "annual_revenue": forecast_result["annual_revenue"],
        "annual_costs": annual_costs,
        "annual_profit": forecast_result["annual_profit"],
        "profit_margin": forecast_result["profit_margin"],
        "risk_level": forecast_result["risk_level"],
        "revenue_per_cow": forecast_result["revenue_per_cow"],
        "profit_per_cow": forecast_result["profit_per_cow"],
        "cost_per_cow": cost_per_cow,
        "feed_cost_ratio": forecast_result["feed_cost_ratio"],
        "cost_ratio": forecast_result["cost_ratio"],
        "monthly_cashflow": forecast_result["monthly_cashflow"],
        "lowest_cash_balance": lowest_balance,
        "lowest_cash_balance_month": lowest_month_name,
    }


def print_profitability_dashboard(dashboard):
    """Print the profitability dashboard in a clean advisor-friendly format."""
    print("--------------------------------")
    print("PROFITABILITY DASHBOARD")
    print("--------------------------------")
    print(f"Farm: {dashboard['farm_name']}\n")

    print(f"Annual Revenue: €{dashboard['annual_revenue']:,.0f}")
    print(f"Annual Costs: €{dashboard['annual_costs']:,.0f}")
    print(f"Annual Profit: €{dashboard['annual_profit']:,.0f}")
    print(f"Profit Margin: {dashboard['profit_margin']:.1f}%")
    print(f"Risk Level: {dashboard['risk_level']}\n")

    print(f"Revenue per Cow: €{dashboard['revenue_per_cow']:,.0f}")
    print(f"Cost per Cow: €{dashboard['cost_per_cow']:,.0f}")
    print(f"Profit per Cow: €{dashboard['profit_per_cow']:,.0f}\n")

    print(f"Feed Cost Ratio: {dashboard['feed_cost_ratio']:.1f}%")
    print(f"Total Cost Ratio: {dashboard['cost_ratio']:.1f}%")
    print(
        f"Average Monthly Cashflow: €{dashboard['monthly_cashflow']:,.0f}\n"
    )

    print(f"Lowest Cash Balance: €{dashboard['lowest_cash_balance']:,.0f}")
    print(f"Lowest Cash Balance Month: {dashboard['lowest_cash_balance_month']}")
    print("--------------------------------")
