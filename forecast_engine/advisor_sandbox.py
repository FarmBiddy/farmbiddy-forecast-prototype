import copy
import json
import os
from datetime import datetime

from config.paths import SANDBOX_DIR, ensure_output_dirs
from forecast_engine.revenue import calculate_revenue
from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.cashflow import calculate_monthly_cashflow, generate_monthly_forecast
from forecast_engine.alerts import generate_alerts
from forecast_engine.risk_level import calculate_risk_level


def _apply_percentage_change(current_value, percentage_change):
    """Increase or decrease a value by a percentage."""
    return current_value * (1 + percentage_change / 100)


def _read_float(prompt):
    """Read a number from the user and handle invalid input."""
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Please enter a valid number.")


def _read_int(prompt):
    """Read a whole number from the user and handle invalid input."""
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Please enter a valid whole number.")


def _record_change(changes_made, field_name, change_type, old_value, new_value, extra=None):
    """
    Keep a readable history of what the advisor changed.
    This is saved with the sandbox scenario if the user chooses to save it.
    """
    change_record = {
        "type": change_type,
        "from": old_value,
        "to": new_value,
    }

    if extra:
        change_record.update(extra)

    changes_made[field_name] = change_record


def _modify_cost_field(sandbox_farm, changes_made, field_name, label):
    """
    Let the advisor change a cost using either:
    - a percentage change (for example +20%)
    - a direct new value
    """
    current_value = sandbox_farm[field_name]

    print(f"\n{label} Current: €{current_value:,.2f}")
    print("1. Percentage Change")
    print("2. New Value")

    option = input("Choose option: ").strip()

    if option == "1":
        percentage_change = _read_float(
            "Enter percentage change (example: 20 for +20%, -12 for -12%): "
        )
        new_value = _apply_percentage_change(current_value, percentage_change)
        _record_change(
            changes_made,
            field_name,
            "percentage_change",
            current_value,
            new_value,
            {"percentage_change": percentage_change},
        )
    elif option == "2":
        new_value = _read_float(f"Enter new {label.lower()} value: €")
        _record_change(
            changes_made,
            field_name,
            "new_value",
            current_value,
            new_value,
        )
    else:
        print("No change made.")
        return

    sandbox_farm[field_name] = round(new_value, 2)
    print(f"Updated {label}: €{sandbox_farm[field_name]:,.2f}")


def _modify_milk_price(sandbox_farm, changes_made):
    """Let the advisor change milk price by percentage or direct value."""
    current_value = sandbox_farm["milk_price"]

    print(f"\nMilk Price Current: €{current_value:.4f}")
    print("1. Percentage Change")
    print("2. New Milk Price")

    option = input("Choose option: ").strip()

    if option == "1":
        percentage_change = _read_float(
            "Enter percentage change (example: -12 for a 12% fall): "
        )
        new_value = _apply_percentage_change(current_value, percentage_change)
        _record_change(
            changes_made,
            "milk_price",
            "percentage_change",
            current_value,
            new_value,
            {"percentage_change": percentage_change},
        )
    elif option == "2":
        new_value = _read_float("Enter new milk price: €")
        _record_change(
            changes_made,
            "milk_price",
            "new_value",
            current_value,
            new_value,
        )
    else:
        print("No change made.")
        return

    sandbox_farm["milk_price"] = round(new_value, 4)
    print(f"Updated Milk Price: €{sandbox_farm['milk_price']:.4f}")


def _modify_direct_value(sandbox_farm, changes_made, field_name, label, decimal_places=2):
    """Change a field by entering one new value directly."""
    current_value = sandbox_farm.get(field_name, 0)

    print(f"\n{label} Current: {current_value}")
    new_value = _read_float(f"Enter new {label.lower()}: ")

    _record_change(
        changes_made,
        field_name,
        "new_value",
        current_value,
        new_value,
    )

    if decimal_places == 0:
        sandbox_farm[field_name] = int(new_value)
    else:
        sandbox_farm[field_name] = round(new_value, decimal_places)

    print(f"Updated {label}: {sandbox_farm[field_name]}")


def _modify_scheme_payment(sandbox_farm, changes_made, field_name, label):
    """
    Change a scheme payment amount.
    Also allows the advisor to delay the payment month, which helps answer
  questions like 'What if scheme payments are delayed?'
    """
    current_value = sandbox_farm.get(field_name, 0)

    if "scheme_payment_months" not in sandbox_farm:
        sandbox_farm["scheme_payment_months"] = {}

    current_month = sandbox_farm["scheme_payment_months"].get(field_name, 12)

    print(f"\n{label} Current: €{current_value:,.2f}")
    print(f"Payment Month Current: {current_month}")

    new_value = _read_float(f"Enter new {label} value: €")

    _record_change(
        changes_made,
        field_name,
        "new_value",
        current_value,
        new_value,
    )

    sandbox_farm[field_name] = round(new_value, 2)
    print(f"Updated {label}: €{sandbox_farm[field_name]:,.2f}")

    delay_payment = input("Change payment month? (y/n): ").strip().lower()

    if delay_payment == "y":
        new_month = _read_int("Enter new payment month (1-12): ")

        if new_month < 1 or new_month > 12:
            print("Invalid month. Payment month was not changed.")
            return

        old_month = current_month
        sandbox_farm["scheme_payment_months"][field_name] = new_month

        month_field_name = f"{field_name}_payment_month"
        _record_change(
            changes_made,
            month_field_name,
            "new_value",
            old_month,
            new_month,
        )

        print(f"Updated {label} payment month to: {new_month}")


def _show_sandbox_menu(sandbox_farm, changes_made):
    """Display the sandbox menu and show how many changes have been made."""
    print("\n---")
    print("## ADVISOR SANDBOX")
    print("---")
    print(f"Farm: {sandbox_farm['farm_name']}")
    print(f"Changes made so far: {len(changes_made)}")
    print("\nSelect assumptions to modify:")
    print("1. Milk Price")
    print("2. Feed Cost")
    print("3. Fertiliser Cost")
    print("4. Labour Cost")
    print("5. Loan Repayments")
    print("6. Number of Cows")
    print("7. Litres per Cow")
    print("8. Opening Cash Balance")
    print("9. BISS Payment")
    print("10. ACRES Payment")
    print("11. Run Forecast")
    print("12. Cancel")


def _calculate_sandbox_forecast(sandbox_farm):
    """
    Reuse the existing forecast engine functions.
    We do not duplicate business logic here.
    """
    revenue = calculate_revenue(sandbox_farm)
    costs = calculate_costs(sandbox_farm)
    profit = calculate_profit(revenue, costs)
    profit_margin = profit / revenue if revenue > 0 else 0

    monthly_cashflow = calculate_monthly_cashflow(revenue, costs)
    alerts = generate_alerts(
        sandbox_farm,
        profit,
        revenue,
        costs,
        monthly_cashflow,
    )
    risk_level = calculate_risk_level(alerts, profit_margin)
    monthly_forecast = generate_monthly_forecast(
        sandbox_farm,
        revenue,
        costs,
        sandbox_farm.get("opening_cash_balance", 0),
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "farm_name": sandbox_farm["farm_name"],
        "annual_revenue": round(revenue, 2),
        "annual_costs": round(costs, 2),
        "annual_profit": round(profit, 2),
        "profit_margin": round(profit_margin * 100, 2),
        "monthly_cashflow": round(monthly_cashflow, 2),
        "risk_level": risk_level,
        "alerts": alerts,
        "monthly_forecast": monthly_forecast,
    }


def _print_sandbox_results(forecast_result):
    """Display the sandbox forecast in a clear advisor-friendly format."""
    print("\n---")
    print("## SANDBOX RESULTS")
    print("---")
    print("Revenue: €", forecast_result["annual_revenue"])
    print("Costs: €", forecast_result["annual_costs"])
    print("Profit: €", forecast_result["annual_profit"])
    print("Profit Margin:", forecast_result["profit_margin"], "%")
    print("Monthly Cashflow: €", forecast_result["monthly_cashflow"])
    print("Risk Level:", forecast_result["risk_level"])
    print("\nAlerts:")

    if forecast_result["alerts"]:
        for alert in forecast_result["alerts"]:
            print("-", alert)
    else:
        print("- No major alerts.")


def _save_sandbox_scenario(sandbox_result):
    """Save the sandbox scenario JSON into the sandbox output folder."""
    ensure_output_dirs()

    farm_name = (
        sandbox_result["forecast_result"]["farm_name"]
        .lower()
        .replace(" ", "_")
    )
    scenario_name = (
        sandbox_result["scenario_name"]
        .lower()
        .replace(" ", "_")
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(
        SANDBOX_DIR,
        f"{farm_name}_{scenario_name}_{timestamp}.json",
    )

    with open(output_path, "w") as file:
        json.dump(sandbox_result, file, indent=4)

    print("\nSandbox scenario saved to:", output_path)
    return output_path


def _run_sandbox_forecast(sandbox_farm, changes_made):
    """Calculate, display, and optionally save the sandbox forecast."""
    if not changes_made:
        print("\nNo assumptions were changed yet.")
        continue_anyway = input("Run forecast anyway? (y/n): ").strip().lower()

        if continue_anyway != "y":
            return None

    forecast_result = _calculate_sandbox_forecast(sandbox_farm)
    _print_sandbox_results(forecast_result)

    scenario_name = f"{sandbox_farm['farm_name']}_sandbox"

    sandbox_result = {
        "scenario_name": scenario_name,
        "changes_made": changes_made,
        "forecast_result": forecast_result,
    }

    save_choice = input("\nWould you like to save this scenario? (y/n): ").strip().lower()

    if save_choice == "y":
        custom_name = input("Enter a scenario name: ").strip()

        if custom_name:
            sandbox_result["scenario_name"] = custom_name

        _save_sandbox_scenario(sandbox_result)

    return sandbox_result


def run_advisor_sandbox(farm):
    """
    Interactive sandbox mode for agricultural advisors.

    The advisor can change multiple assumptions, then run a forecast
    without changing the original farm JSON file.
    """
    # Work on a copy so the original farm data is never modified.
    sandbox_farm = copy.deepcopy(farm)
    changes_made = {}

    print("\nWelcome to Advisor Sandbox Mode.")
    print("You can change assumptions and explore 'what if' questions safely.")

    while True:
        _show_sandbox_menu(sandbox_farm, changes_made)
        choice = input("Select option: ").strip()

        if choice == "1":
            _modify_milk_price(sandbox_farm, changes_made)
        elif choice == "2":
            _modify_cost_field(sandbox_farm, changes_made, "feed", "Feed Cost")
        elif choice == "3":
            _modify_cost_field(
                sandbox_farm,
                changes_made,
                "fertiliser",
                "Fertiliser Cost",
            )
        elif choice == "4":
            _modify_cost_field(sandbox_farm, changes_made, "labour", "Labour Cost")
        elif choice == "5":
            _modify_cost_field(
                sandbox_farm,
                changes_made,
                "loan_repayments",
                "Loan Repayments",
            )
        elif choice == "6":
            _modify_direct_value(
                sandbox_farm,
                changes_made,
                "milking_cows",
                "Number of Cows",
                decimal_places=0,
            )
        elif choice == "7":
            _modify_direct_value(
                sandbox_farm,
                changes_made,
                "litres_per_cow",
                "Litres per Cow",
            )
        elif choice == "8":
            _modify_direct_value(
                sandbox_farm,
                changes_made,
                "opening_cash_balance",
                "Opening Cash Balance",
            )
        elif choice == "9":
            _modify_scheme_payment(sandbox_farm, changes_made, "biss", "BISS Payment")
        elif choice == "10":
            _modify_scheme_payment(sandbox_farm, changes_made, "acres", "ACRES Payment")
        elif choice == "11":
            return _run_sandbox_forecast(sandbox_farm, changes_made)
        elif choice == "12":
            print("Sandbox cancelled.")
            return None
        else:
            print("Invalid option. Please choose a number from 1 to 12.")
