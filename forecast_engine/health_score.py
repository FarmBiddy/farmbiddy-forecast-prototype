"""Canonical farm financial-health score (UX items 4-5).

This is the single source of truth for the 0-100 health score and its
profitability/cashflow/feed-pressure/debt-pressure/risk breakdown. Every
surface that shows a health score or status (Farm Intelligence, the
executive dashboard snapshot, the advisor chatbot) calls this function
instead of computing its own number, so they can never disagree.

Pure function: takes plain `forecast` and `farm` dicts, returns a plain
dict. No I/O, no other service dependencies, so any module can import it
without risking a circular import.
"""

from __future__ import annotations


def calculate_health_score(forecast: dict, farm: dict) -> dict:
    score = 70
    margin = forecast.get("profit_margin", 0)
    risk = forecast.get("risk_level", "Medium")
    feed = forecast.get("feed_cost_ratio", 35)
    monthly_cf = forecast.get("monthly_cashflow", 0)
    opening = farm.get("opening_cash_balance", 0)
    loans = farm.get("loan_repayments", 0)
    revenue = forecast.get("annual_revenue", 1)

    if margin >= 20:
        score += 12
    elif margin >= 10:
        score += 5
    elif margin < 5:
        score -= 15

    if risk == "Low":
        score += 10
    elif risk == "High":
        score -= 20
    elif risk == "Medium":
        score -= 5

    if feed > 40:
        score -= 12
    elif feed > 35:
        score -= 6
    elif feed <= 30:
        score += 5

    if monthly_cf < 0:
        score -= 15
    elif monthly_cf > 3000:
        score += 5

    if opening < forecast.get("annual_costs", 0) / 12:
        score -= 8

    loan_pct = (loans / revenue * 100) if revenue else 0
    if loan_pct > 15:
        score -= 8

    score = max(0, min(100, score))
    label = "Excellent" if score >= 85 else "Good" if score >= 70 else "Fair" if score >= 50 else "Needs attention"

    return {
        "score": score,
        "label": label,
        "profitability": "Good" if margin >= 15 else "Fair" if margin >= 8 else "Weak",
        "cashflow": "Good" if monthly_cf >= 2000 else "Tight" if monthly_cf >= 0 else "Negative",
        "feed_pressure": "High" if feed > 35 else "Moderate" if feed > 30 else "Low",
        "debt_pressure": "High" if loan_pct > 15 else "Moderate" if loan_pct > 10 else "Low",
        "risk_level": risk,
    }
