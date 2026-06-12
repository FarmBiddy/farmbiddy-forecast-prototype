def calculate_risk_level(alerts, profit_margin):
    risk_score = 0

    critical_keywords = [
        "Negative profit",
        "Negative monthly cashflow"
    ]

    for alert in alerts:
        for keyword in critical_keywords:
            if keyword in alert:
                return "High"

    if profit_margin < 0.10:
        risk_score += 3
    elif profit_margin < 0.20:
        risk_score += 1

    if len(alerts) >= 3:
        risk_score += 3
    elif len(alerts) >= 1:
        risk_score += 1

    if risk_score >= 4:
        return "High"

    if risk_score >= 2:
        return "Medium"

    return "Low"
    