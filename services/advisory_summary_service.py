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


def _profitability_label(profit_margin):
    if profit_margin >= 20:
        return "strong"
    if profit_margin >= 10:
        return "moderate"
    return "weak"


def _profit_outlook(annual_profit):
    if annual_profit > 0:
        return "remain profitable"
    if annual_profit < 0:
        return "make a loss"
    return "break even"


def _risk_recommendation(risk_level):
    if risk_level == "High":
        return (
            "The advisor should review this forecast urgently with the farmer "
            "and agree immediate actions to protect cashflow and profitability."
        )
    if risk_level == "Medium":
        return (
            "The advisor should monitor key risks closely and review the forecast "
            "again before major spending or borrowing decisions."
        )
    return (
        "No major immediate issues are flagged, but the advisor should still "
        "review the forecast as part of routine farm planning."
    )


def _find_lowest_balance_month(monthly_forecast):
    lowest_month = min(
        monthly_forecast,
        key=lambda month: month["running_balance"],
    )

    month_number = lowest_month["month"]
    month_name = MONTH_NAMES[month_number]

    return month_name, lowest_month["running_balance"]


def _has_cash_pressure(forecast_result, farm, lowest_balance):
    monthly_costs = forecast_result["annual_costs"] / 12
    opening_balance = farm.get("opening_cash_balance", 0)

    if forecast_result["monthly_cashflow"] < 0:
        return True

    if lowest_balance < monthly_costs:
        return True

    if opening_balance < monthly_costs:
        return True

    return False


def _build_key_strengths(forecast_result):
    strengths = []

    if forecast_result["annual_profit"] > 0:
        strengths.append(
            "The farm remains profitable over the forecast period."
        )

    if forecast_result["profit_margin"] >= 20:
        strengths.append(
            f"Profitability is strong at {forecast_result['profit_margin']}% margin."
        )

    if forecast_result["monthly_cashflow"] > 0:
        strengths.append(
            "Average monthly cashflow is positive."
        )

    if forecast_result["revenue_per_cow"] > 0:
        strengths.append(
            f"Revenue per cow is €{forecast_result['revenue_per_cow']:,.2f}."
        )

    if forecast_result["profit_per_cow"] > 0:
        strengths.append(
            f"Profit per cow is €{forecast_result['profit_per_cow']:,.2f}."
        )

    if forecast_result["feed_cost_ratio"] <= 35:
        strengths.append(
            "Feed costs are within a manageable range relative to revenue."
        )

    if forecast_result["risk_level"] == "Low":
        strengths.append(
            "The overall risk level is low based on current forecast alerts."
        )

    if not strengths:
        strengths.append(
            "The forecast provides a clear baseline for advisor review and planning."
        )

    return strengths


def _alert_to_concern(alert):
    if alert.startswith("Negative profit"):
        return "The farm is forecasted to make an annual loss."
    if alert.startswith("Low profit margin"):
        return "Profit margin is below the recommended level."
    if alert.startswith("High feed cost percentage"):
        return "Feed costs are above the recommended threshold."
    if alert.startswith("Negative monthly cashflow"):
        return "Monthly cashflow is negative across the forecast period."
    if alert.startswith("Low cash balance"):
        return "Cash balance is tight and may not cover one month of operating costs."
    return alert


def _build_key_concerns(forecast_result, cash_pressure, lowest_month_name):
    concerns = []

    for alert in forecast_result["alerts"]:
        concern = _alert_to_concern(alert)
        if concern not in concerns:
            concerns.append(concern)

    if cash_pressure and not any("cash" in concern.lower() for concern in concerns):
        concerns.append(
            f"Cash pressure appears during the forecast, especially around {lowest_month_name}."
        )

    if not concerns:
        concerns.append(
            "No major concerns are flagged, but margins and costs should still be monitored."
        )

    return concerns


def _build_cashflow_commentary(
    forecast_result,
    lowest_month_name,
    lowest_balance,
    cash_pressure,
):
    balance_text = (
        f"The lowest projected cash balance occurs in {lowest_month_name} "
        f"at €{lowest_balance:,.2f}."
    )

    if cash_pressure:
        return (
            f"{balance_text} Cash pressure appears in at least one month, "
            "so reserves should be monitored closely."
        )

    return (
        f"{balance_text} Cash reserves appear stable across the forecast period."
    )


def _build_risk_commentary(forecast_result):
    risk_level = forecast_result["risk_level"]
    profitability = _profitability_label(forecast_result["profit_margin"])

    reasons = []

    if forecast_result["annual_profit"] < 0:
        reasons.append("forecasted loss")

    if forecast_result["profit_margin"] < 10:
        reasons.append("weak profit margin")
    elif forecast_result["profit_margin"] < 20:
        reasons.append("moderate profit margin")

    if forecast_result["feed_cost_ratio"] > 35:
        reasons.append("feed cost pressure")

    if forecast_result["monthly_cashflow"] < 0:
        reasons.append("negative monthly cashflow")

    if forecast_result["alerts"]:
        reasons.append(f"{len(forecast_result['alerts'])} active alert(s)")

    if reasons:
        reason_text = ", ".join(reasons)
        return (
            f"The overall risk level is {risk_level} due to {reason_text}."
        )

    return (
        f"The overall risk level is {risk_level} with {profitability} profitability."
    )


def _build_advisor_recommendation(forecast_result, farm, cash_pressure):
    recommendations = []

    if forecast_result["feed_cost_ratio"] > 35:
        recommendations.append("monitor feed costs")

    if cash_pressure:
        recommendations.append("review cash reserves")

    scheme_months = farm.get("scheme_payment_months", {})
    if scheme_months and cash_pressure:
        recommendations.append(
            "plan cashflow around the timing of scheme payments"
        )

    if forecast_result["profit_margin"] < 10:
        recommendations.append("review cost control and milk price sensitivity")

    if forecast_result["annual_profit"] < 0:
        recommendations.append(
            "urgently review the farm's cost base and income assumptions"
        )

    if not recommendations:
        return _risk_recommendation(forecast_result["risk_level"])

    action_text = ", ".join(recommendations)

    if forecast_result["risk_level"] == "High":
        return (
            f"The advisor should urgently {action_text} with the farmer."
        )

    return (
        f"The advisor should {action_text}, especially before major farm decisions."
    )


def generate_advisory_summary(forecast_result, farm):
    farm_name = forecast_result["farm_name"]
    annual_profit = forecast_result["annual_profit"]
    profit_margin = forecast_result["profit_margin"]
    risk_level = forecast_result["risk_level"]

    profitability = _profitability_label(profit_margin)
    profit_outlook = _profit_outlook(annual_profit)

    lowest_month_name, lowest_balance = _find_lowest_balance_month(
        forecast_result["monthly_forecast"]
    )
    cash_pressure = _has_cash_pressure(forecast_result, farm, lowest_balance)

    headline = (
        f"{farm_name} is forecasted to {profit_outlook}, "
        f"with {risk_level.lower()} risk."
    )

    financial_position = (
        f"Annual profit is €{annual_profit:,.2f} "
        f"with a {profitability} profit margin of {profit_margin}%."
    )

    cashflow_commentary = _build_cashflow_commentary(
        forecast_result,
        lowest_month_name,
        lowest_balance,
        cash_pressure,
    )

    risk_commentary = _build_risk_commentary(forecast_result)

    key_strengths = _build_key_strengths(forecast_result)
    key_concerns = _build_key_concerns(
        forecast_result,
        cash_pressure,
        lowest_month_name,
    )

    advisor_recommendation = _build_advisor_recommendation(
        forecast_result,
        farm,
        cash_pressure,
    )

    return {
        "headline": headline,
        "financial_position": financial_position,
        "cashflow_commentary": cashflow_commentary,
        "risk_commentary": risk_commentary,
        "key_strengths": key_strengths,
        "key_concerns": key_concerns,
        "advisor_recommendation": advisor_recommendation,
    }


def print_advisory_summary(advisory_summary):
    print("\nADVISORY SUMMARY")
    print("=" * 50)
    print("Headline:", advisory_summary["headline"])
    print("\nFinancial Position:")
    print(advisory_summary["financial_position"])
    print("\nCashflow Commentary:")
    print(advisory_summary["cashflow_commentary"])
    print("\nRisk Commentary:")
    print(advisory_summary["risk_commentary"])
    print("\nKey Strengths:")
    for strength in advisory_summary["key_strengths"]:
        print("-", strength)
    print("\nKey Concerns:")
    for concern in advisory_summary["key_concerns"]:
        print("-", concern)
    print("\nAdvisor Recommendation:")
    print(advisory_summary["advisor_recommendation"])
