"""
Top Risk Drivers — identify the biggest factors contributing to farm risk.

Uses existing forecast KPIs and results rather than re-running alert logic.
"""

from forecast_engine.kpis import calculate_feed_cost_ratio

# Used when sorting drivers: High first, then Medium, then Low.
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _ratio_pct(cost, revenue):
    """Return cost as a percentage of revenue, or 0 when revenue is missing."""
    if revenue <= 0:
        return 0.0
    return round(cost / revenue * 100, 2)


def _score_feed_ratio(pct):
    if pct > 40:
        return "High"
    if pct >= 30:
        return "Medium"
    return "Low"


def _score_labour_ratio(pct):
    if pct > 20:
        return "High"
    if pct >= 15:
        return "Medium"
    return "Low"


def _score_loan_ratio(pct):
    if pct > 15:
        return "High"
    if pct >= 10:
        return "Medium"
    return "Low"


def _score_fertiliser_ratio(pct):
    # No published threshold in the spec — sensible dairy-farm benchmarks.
    if pct > 12:
        return "High"
    if pct >= 8:
        return "Medium"
    return "Low"


def _score_profit_margin(pct):
    # Lower margin = higher risk (inverted scale).
    if pct < 10:
        return "High"
    if pct <= 20:
        return "Medium"
    return "Low"


def _score_monthly_cashflow(monthly_cashflow):
    if monthly_cashflow < 0:
        return "High"
    return "Low"


def _score_alert_count(alert_count):
    if alert_count >= 3:
        return "High"
    if alert_count >= 1:
        return "Medium"
    return "Low"


def _feed_commentary(pct, risk):
    if risk == "High":
        return (
            f"Feed costs represent {pct}% of revenue and are placing "
            "pressure on profitability."
        )
    if risk == "Medium":
        return (
            f"Feed costs represent {pct}% of revenue and should be monitored."
        )
    return f"Feed costs represent {pct}% of revenue."


def _labour_commentary(pct, risk):
    if risk in ("High", "Medium"):
        return f"Labour costs absorb {pct}% of annual revenue."
    return f"Labour costs are {pct}% of annual revenue."


def _loan_commentary(pct, risk):
    if risk in ("High", "Medium"):
        return f"Debt servicing absorbs {pct}% of annual revenue."
    return f"Loan repayments are {pct}% of annual revenue."


def _fertiliser_commentary(pct, risk):
    if risk in ("High", "Medium"):
        return (
            f"Fertiliser costs represent {pct}% of revenue and add "
            "to operating pressure."
        )
    return f"Fertiliser costs represent {pct}% of revenue."


def _profit_margin_commentary(pct, risk):
    if risk == "High":
        return f"Profit margin is critically low at {pct}%."
    if risk == "Medium":
        return "Profit margin is below the preferred target."
    return f"Profit margin is {pct}%."


def _cashflow_commentary(monthly_cashflow, risk):
    if risk == "High":
        return (
            "Monthly cashflow is negative, indicating costs exceed "
            "income on average."
        )
    return f"Average monthly cashflow is positive at €{monthly_cashflow:,.2f}."


def _risk_level_commentary(risk_level):
    if risk_level == "High":
        return (
            "The overall forecast risk level is High and warrants "
            "urgent advisor review."
        )
    if risk_level == "Medium":
        return (
            "The overall forecast risk level is Medium and should be "
            "monitored closely."
        )
    return "The overall forecast risk level is Low."


def _alerts_commentary(alert_count):
    if alert_count == 1:
        return "The forecast has 1 active alert requiring advisor attention."
    if alert_count > 1:
        return (
            f"The forecast has {alert_count} active alerts requiring "
            "advisor attention."
        )
    return "No active forecast alerts."


def calculate_risk_drivers(farm, forecast_result):
    """
    Analyse key financial factors and return the top 3 risk drivers.

    Reads KPIs and results already computed in the forecast pipeline
    (profit margin, cashflow, risk level, alerts) and adds cost ratios
    from the farm data where needed.
    """
    revenue = forecast_result["annual_revenue"]

    # --- Cost ratios (% of revenue) ---
    feed_pct = forecast_result.get("feed_cost_ratio")
    if feed_pct is None and revenue > 0:
        feed_pct = round(calculate_feed_cost_ratio(farm, revenue) * 100, 2)
    feed_pct = feed_pct or 0.0

    labour_pct = _ratio_pct(farm["labour"], revenue)
    loan_pct = _ratio_pct(farm["loan_repayments"], revenue)
    fertiliser_pct = _ratio_pct(farm["fertiliser"], revenue)

    # --- Existing forecast KPIs ---
    profit_margin = forecast_result["profit_margin"]
    monthly_cashflow = forecast_result["monthly_cashflow"]
    risk_level = forecast_result["risk_level"]
    alerts = forecast_result.get("alerts", [])
    alert_count = len(alerts)

    # --- Score each factor and build candidate list ---
    feed_risk = _score_feed_ratio(feed_pct)
    labour_risk = _score_labour_ratio(labour_pct)
    loan_risk = _score_loan_ratio(loan_pct)
    fertiliser_risk = _score_fertiliser_ratio(fertiliser_pct)
    margin_risk = _score_profit_margin(profit_margin)
    cashflow_risk = _score_monthly_cashflow(monthly_cashflow)
    alerts_risk = _score_alert_count(alert_count)

    candidates = [
        {
            "driver": "Feed Costs",
            "value": feed_pct,
            "risk": feed_risk,
            "commentary": _feed_commentary(feed_pct, feed_risk),
        },
        {
            "driver": "Labour Costs",
            "value": labour_pct,
            "risk": labour_risk,
            "commentary": _labour_commentary(labour_pct, labour_risk),
        },
        {
            "driver": "Loan Repayments",
            "value": loan_pct,
            "risk": loan_risk,
            "commentary": _loan_commentary(loan_pct, loan_risk),
        },
        {
            "driver": "Fertiliser Costs",
            "value": fertiliser_pct,
            "risk": fertiliser_risk,
            "commentary": _fertiliser_commentary(fertiliser_pct, fertiliser_risk),
        },
        {
            "driver": "Profit Margin",
            "value": profit_margin,
            "risk": margin_risk,
            "commentary": _profit_margin_commentary(profit_margin, margin_risk),
        },
        {
            "driver": "Monthly Cashflow",
            "value": monthly_cashflow,
            "risk": cashflow_risk,
            "commentary": _cashflow_commentary(monthly_cashflow, cashflow_risk),
        },
        {
            "driver": "Overall Risk Level",
            "value": SEVERITY_ORDER.get(risk_level, 2),
            "risk": risk_level,
            "commentary": _risk_level_commentary(risk_level),
        },
        {
            "driver": "Active Alerts",
            "value": alert_count,
            "risk": alerts_risk,
            "commentary": _alerts_commentary(alert_count),
        },
    ]

    # Only Medium and High factors are "significant" risk drivers.
    significant = [d for d in candidates if d["risk"] in ("High", "Medium")]

    # Sort by severity, then by value (higher ratio / count = more pressing).
    significant.sort(
        key=lambda d: (
            SEVERITY_ORDER[d["risk"]],
            -(d["value"] if isinstance(d["value"], (int, float)) else 0),
        )
    )

    # Return top 3 only, without the internal value field in output.
    top_three = []
    for driver in significant[:3]:
        top_three.append({
            "driver": driver["driver"],
            "risk": driver["risk"],
            "commentary": driver["commentary"],
        })

    return top_three


def print_top_risk_drivers(risk_drivers):
    """Print risk drivers in an advisor-friendly numbered list."""
    print("\n---")
    print("\n## TOP RISK DRIVERS\n")

    if not risk_drivers:
        print("No major risk drivers identified.")
        return

    for index, driver in enumerate(risk_drivers, start=1):
        print(f"{index}. {driver['driver']} ({driver['risk']})")
        print(f"   {driver['commentary']}\n")
