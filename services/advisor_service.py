"""
Farm Intelligence advisor — rule-based question routing.

Routes farmer questions to existing forecast, intelligence, and sandbox services.
Scenario questions parse natural language into sandbox inputs and return sector-aware
impact breakdowns (direct sector vs overall farm vs unaffected sectors).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from services.dashboard_summary import calculate_sector_performance, get_selected_sector_data
from services.farmer_dashboard_service import resolve_farm_file, resolve_sectors
from services.financial_intelligence_service import (
    _health_score,
    _load_forecast_context,
    _plain_summary,
    get_financial_intelligence,
)
from models.multi_sector_farm import VALID_SECTORS
from services.multi_sector_farm import load_farm_for_analysis
from services.scenario_sandbox_service import run_scenario_sandbox

Handler = Callable[..., dict[str, Any]]

MONTH_LABELS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def detect_intent(question: str) -> str:
    """Rule-based intent detection — first match wins (most specific patterns first)."""
    q = _normalize_question(question)
    if not q:
        return "general_recommendation"

    if "what should i do next" in q:
        return "general_recommendation"

    if "explain" in q and "simpler" in q:
        return "general_recommendation"

    if ("cow" in q or "cows" in q or "herd" in q) and any(
        w in q for w in ("add", "increase", "more", "what if", "what happens", "expand")
    ):
        return "scenario_herd_size"

    milk_scenario = (
        "milk price" in q
        or "c/l" in q
        or re.search(r"(\d+(?:\.\d+)?)\s*(?:c/l|cents?|cent(?!\w))", q)
        or ("milk" in q and any(w in q for w in ("increase", "decrease", "rise", "fall", "drop", "what if", "what happens")))
    )
    if milk_scenario and "feed" not in q:
        return "scenario_milk_price"

    if "feed" in q and any(
        w in q for w in ("%", "percent", "increase", "decrease", "rise", "fall", "what if", "what happens", "cost")
    ):
        return "scenario_feed_cost"

    if ("labour" in q or "labor" in q) and any(
        w in q for w in ("%", "percent", "increase", "decrease", "rise", "fall", "what if", "what happens", "cost")
    ):
        return "scenario_labour_cost"

    if any(w in q for w in ("health score", "how healthy", "explain my health")):
        return "health_score"

    if any(w in q for w in ("strength", "doing well", "key strength")):
        return "strengths"

    if any(w in q for w in ("biggest risk", "financial risk", "main risk")) or (
        "risk" in q and any(w in q for w in ("what are", "biggest", "main"))
    ):
        return "risks"

    if any(w in q for w in ("which sector", "performing best", "best sector", "worst sector")):
        return "sector_comparison"

    if "cashflow" in q or "cash flow" in q:
        return "cashflow_forecast"

    if any(w in q for w in ("funding", "additional funding", "need a loan", "need funding")) or (
        "loan" in q and "what if" not in q
    ):
        return "funding_need"

    if any(w in q for w in ("losing money", "lose money", "losing the most", "improve profit", "profitability", "profit margin")) or (
        "profit" in q and "what if" not in q and "what happens" not in q
    ):
        return "profitability"

    return "general_recommendation"


def resolve_affected_sectors(intent: str, selected: list[str]) -> tuple[list[str], list[str]]:
    """Map intent to directly affected sectors vs unaffected selected sectors."""
    selected_set = list(dict.fromkeys(selected))

    if intent == "scenario_milk_price":
        affected = [s for s in selected_set if s == "dairy"]
        return affected, [s for s in selected_set if s not in affected]

    if intent == "scenario_feed_cost":
        return selected_set, []

    if intent in ("scenario_labour_cost",):
        return selected_set, []

    if intent == "scenario_herd_size":
        affected = [s for s in selected_set if s == "dairy"]
        return affected, [s for s in selected_set if s not in affected]

    if intent in {
        "health_score",
        "strengths",
        "risks",
        "profitability",
        "sector_comparison",
        "cashflow_forecast",
        "general_recommendation",
    }:
        return selected_set, []

    if intent == "funding_need":
        return [], selected_set

    return selected_set, []


def _empty_sector_metrics() -> dict[str, Any]:
    return {
        "revenue_change": None,
        "profit_change": None,
        "cashflow_change": None,
        "margin_change": None,
    }


def _sector_impact_for(sectors: list[str]) -> dict[str, Any]:
    return {sector: dict(_empty_sector_metrics()) for sector in sectors}


def _empty_overall_impact() -> dict[str, Any]:
    return {
        "total_revenue_change": None,
        "total_profit_change": None,
        "health_score_before": None,
        "health_score_after": None,
        "risk_level_before": None,
        "risk_level_after": None,
    }


def _sector_label(sector_id: str) -> str:
    labels = {"dairy": "Dairy", "beef": "Beef", "lamb": "Lamb"}
    return labels.get(sector_id, sector_id.title())


def _unaffected_note(affected: list[str], unaffected: list[str]) -> str:
    if not unaffected:
        return ""
    if not affected:
        return "This applies to your whole farm rather than one sector alone."
    names = ", ".join(_sector_label(s) for s in unaffected)
    return f"{names} {'is' if len(unaffected) == 1 else 'are'} not directly affected by this change."


def _selected_sector_names(selected: list[str]) -> str:
    labels = [_sector_label(sector) for sector in selected]
    if len(labels) <= 1:
        return labels[0] if labels else "your selected sectors"
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _is_whole_farm_selection(selected: list[str]) -> bool:
    return set(selected) == set(VALID_SECTORS)


def _build_scope_summary(
    intent: str,
    affected: list[str],
    unaffected: list[str],
    selected: list[str],
) -> str:
    selected_names = _selected_sector_names(selected)

    if intent == "funding_need":
        return "Scope: whole farm."

    if intent in ("scenario_milk_price", "scenario_herd_size"):
        if not affected:
            return "Scope: dairy only — dairy is not in your current sector selection."
        parts = [f"Direct impact: {_selected_sector_names(affected)}."]
        if unaffected:
            parts.append(f"No direct impact on {_selected_sector_names(unaffected)}.")
        if _is_whole_farm_selection(selected):
            parts.append("Whole-farm totals include all sectors.")
        else:
            parts.append(f"Totals based on selected sectors: {selected_names}.")
        return " ".join(parts)

    if intent in ("scenario_feed_cost", "scenario_labour_cost"):
        scenario_label = "Feed costs" if intent == "scenario_feed_cost" else "Labour costs"
        if _is_whole_farm_selection(selected):
            return f"Scope: whole farm ({selected_names}). {scenario_label} apply to all selected sectors."
        return f"Scope: selected sectors — {selected_names}. {scenario_label} apply to all selected sectors."

    if _is_whole_farm_selection(selected):
        return f"Scope: whole farm ({selected_names})."

    return f"Scope: selected sectors — {selected_names}."


def _base_response(
    question: str,
    intent: str,
    affected: list[str],
    unaffected: list[str],
    selected: list[str],
    *,
    summary: str,
    key_points: list[str],
    recommendation: str,
    sector_impact: dict[str, Any] | None = None,
    overall_impact: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "question": question,
        "intent": intent,
        "affected_sectors": affected,
        "unaffected_sectors": unaffected,
        "selected_sectors": selected,
        "scope_summary": _build_scope_summary(intent, affected, unaffected, selected),
        "sector_impact": sector_impact if sector_impact is not None else _sector_impact_for(affected),
        "overall_impact": overall_impact if overall_impact is not None else _empty_overall_impact(),
        "summary": summary,
        "key_points": key_points,
        "recommendation": recommendation,
        "metrics": metrics or {},
    }


def _load_intel(farm_file: str, selected: list[str]) -> dict[str, Any]:
    return get_financial_intelligence(farm_file, sectors=selected)


def _month_label(month_num: int | float) -> str:
    idx = int(month_num) - 1
    if 0 <= idx < len(MONTH_LABELS):
        return MONTH_LABELS[idx]
    return str(month_num)


def _analyze_monthly_cashflow(monthly: list[dict]) -> dict[str, Any]:
    if not monthly:
        return {}
    points: list[dict[str, Any]] = []
    for index, entry in enumerate(monthly[:12]):
        month = entry.get("month", index + 1)
        points.append({
            "label": _month_label(month) if isinstance(month, (int, float)) else str(month),
            "running_balance": float(entry.get("running_balance") or 0),
            "cashflow": float(entry.get("cashflow") or 0),
        })
    if not points:
        return {}
    min_point = min(points, key=lambda item: item["running_balance"])
    negative = [item["label"] for item in points if item["running_balance"] < 0]
    return {
        "min_month": min_point["label"],
        "min_balance": min_point["running_balance"],
        "negative_months": negative,
        "end_balance": points[-1]["running_balance"],
    }


def _load_advisor_context(farm_file: str, selected: list[str]) -> dict[str, Any]:
    intel = _load_intel(farm_file, selected)
    _, forecast, extras = _load_forecast_context(farm_file, selected)
    monthly = forecast.get("monthly_forecast") or []
    return {
        "intel": intel,
        "forecast": forecast,
        "advisory": extras.get("advisory") or {},
        "monthly_forecast": monthly,
        "cashflow_insights": _analyze_monthly_cashflow(monthly),
    }


def _first_recommendation(intel: dict[str, Any]) -> str:
    actions = intel.get("recommended_actions") or []
    return actions[0]["title"] if actions else "Keep monitoring cash and costs each month."


def _sector_scope_label(selected: list[str]) -> str:
    if _is_whole_farm_selection(selected):
        return "your whole farm"
    if len(selected) == 1:
        return f"{_sector_label(selected[0])} only"
    return _selected_sector_names(selected)


def _format_health_answer(ctx: dict[str, Any]) -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    health = intel["health_score"]
    farm_name = intel.get("farm_name") or "Your farm"
    score = health.get("score", 0)
    label = health.get("label", "—")

    if score >= 85:
        tone = f"{farm_name} is in strong financial shape"
    elif score >= 70:
        tone = f"{farm_name} looks financially stable overall"
    elif score >= 50:
        tone = f"{farm_name} is under some financial pressure"
    else:
        tone = f"{farm_name} needs urgent financial attention"

    summary = f"{tone}, with a health score of {score}/100 ({label})."
    watch: list[str] = []
    if health.get("feed_pressure") == "High":
        watch.append("feed costs are squeezing margins")
    elif health.get("feed_pressure") == "Moderate":
        watch.append("feed costs need watching")
    if health.get("cashflow") == "Negative":
        watch.append("monthly cashflow is negative")
    elif health.get("cashflow") == "Tight":
        watch.append("cashflow is tight")
    if health.get("debt_pressure") == "High":
        watch.append("debt repayments are heavy")

    if watch:
        summary += " Watch out because " + ", ".join(watch) + "."

    risk = intel["forecast_summary"].get("risk_level")
    if risk == "High":
        summary += " Overall risk is elevated — act on costs and cash this month."
    elif risk == "Low":
        summary += " Overall risk is low if you stay disciplined on costs."

    key_points = [
        f"Health score: {score}/100 ({label}).",
        f"Profitability: {health.get('profitability', '—')}.",
        f"Cashflow: {health.get('cashflow', '—')}.",
        f"Feed pressure: {health.get('feed_pressure', '—')}.",
        f"Debt pressure: {health.get('debt_pressure', '—')}.",
    ]
    return summary, key_points[:5], _first_recommendation(intel)


def _format_strengths_answer(ctx: dict[str, Any], selected: list[str]) -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    strengths = intel.get("key_strengths") or []
    opportunities = intel.get("opportunities") or []
    if not strengths:
        strengths = ["No major strengths flagged yet — keep building reserves and tracking costs."]

    if len(strengths) == 1:
        summary = f"Your main financial strength right now is {strengths[0]}"
    else:
        summary = f"Your strongest areas are {strengths[0]} and {strengths[1]}"

    summary += f" on {_sector_scope_label(selected)}."

    key_points = strengths[:5]
    if opportunities and len(key_points) < 5:
        key_points.append(f"Opportunity: {opportunities[0]}")
    return summary, key_points[:5], "Build on these strengths while keeping costs under control."


def _format_risks_answer(ctx: dict[str, Any]) -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    risks = intel.get("biggest_risks") or []
    risk_level = intel["forecast_summary"].get("risk_level", "Medium")
    health = intel["health_score"]

    if risks:
        lead = risks[0]
        summary = (
            f"Your biggest financial risk right now is {lead.get('driver', 'cash pressure')} "
            f"({lead.get('severity', 'Medium')})."
        )
        if len(risks) > 1:
            summary += (
                f" You should also watch {risks[1].get('driver', 'other pressures')} "
                f"({risks[1].get('severity', 'Medium')})."
            )
        if health.get("feed_pressure") == "High":
            summary += " Feed costs are adding to the pressure on margins."
        key_points = [
            f"{item.get('driver', 'Risk')} — {item.get('severity', 'Medium')}"
            + (f": {item.get('commentary')}" if item.get("commentary") else "")
            for item in risks[:5]
        ]
    else:
        summary = f"No critical risks flagged. Overall risk level is {risk_level}."
        key_points = [summary]

    for alert in (intel.get("alerts") or [])[:2]:
        if len(key_points) >= 5:
            break
        if not any(alert.lower() in point.lower() for point in key_points):
            key_points.append(f"Alert: {alert}")

    return summary, key_points[:5], _first_recommendation(intel) or "Address the highest-severity risk first and keep a cash buffer."


def _format_profitability_answer(
    ctx: dict[str, Any],
    question: str,
    farm_file: str,
    selected: list[str],
) -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    forecast = intel["forecast_summary"]
    profit = forecast.get("annual_profit", 0) or 0
    margin = forecast.get("profit_margin", 0) or 0
    monthly_cf = forecast.get("monthly_cashflow", 0) or 0
    question_norm = _normalize_question(question)
    weaknesses = intel.get("key_weaknesses") or []
    opportunities = intel.get("opportunities") or []

    worst = None
    if "losing" in question_norm or "lose money" in question_norm:
        rows = calculate_sector_performance(get_selected_sector_data(farm_file, selected))
        if rows:
            worst = min(rows, key=lambda row: row.get("profit", 0))

    if worst and worst.get("profit", 0) < 0:
        summary = (
            f"The weakest area is {worst['label']}, losing about €{abs(worst['profit']):,.0f} "
            f"over the last 12 months with a {worst['margin_pct']:.1f}% margin."
        )
        recommendation = f"Focus first on improving costs or income in {worst['label']}."
    elif profit < 0:
        summary = (
            f"On current figures {_sector_scope_label(selected)} may lose about "
            f"€{abs(profit):,.0f} per year — review costs and income urgently."
        )
        recommendation = "Focus on the largest cost lines and cashflow before new spending."
    elif "improve" in question_norm:
        summary = (
            f"The farm is profitable at about €{profit:,.0f} per year, but there is still room to improve margins "
            f"({margin:.1f}% today)."
        )
        if weaknesses:
            summary += f" The main pressure area is {weaknesses[0]}."
        recommendation = _first_recommendation(intel)
    else:
        summary = (
            f"The farm is forecast to make about €{profit:,.0f} profit per year "
            f"with a {margin:.1f}% margin on {_sector_scope_label(selected)}."
        )
        recommendation = "Protect margin by monitoring feed and keeping reserves for seasonal dips."

    key_points = [
        f"Annual profit: €{profit:,.0f}.",
        f"Profit margin: {margin:.1f}%.",
        f"Monthly cashflow: €{monthly_cf:,.0f}.",
    ]
    if worst:
        key_points.append(
            f"{worst['label']}: €{worst['profit']:,.0f} profit, {worst['margin_pct']:.1f}% margin."
        )
    elif weaknesses:
        key_points.append(f"Pressure area: {weaknesses[0]}.")
    if opportunities and len(key_points) < 5:
        key_points.append(f"Opportunity: {opportunities[0]}.")

    return summary, key_points[:5], recommendation


def _format_sector_comparison_answer(
    rows: list[dict],
) -> tuple[str, list[str], str]:
    best = max(rows, key=lambda row: row.get("profit", 0))
    worst = min(rows, key=lambda row: row.get("profit", 0))
    summary = (
        f"{best['label']} is performing best with about €{best['profit']:,.0f} profit "
        f"and a {best['margin_pct']:.1f}% margin over the last 12 months."
    )
    if len(rows) > 1 and worst["sector"] != best["sector"]:
        summary += (
            f" {worst['label']} is the weakest at €{worst['profit']:,.0f} profit "
            f"({worst['margin_pct']:.1f}% margin)."
        )

    key_points = [
        f"{row['label']}: €{row['profit']:,.0f} profit, {row['margin_pct']:.1f}% margin ({row['status']})"
        for row in rows
    ]
    recommendation = (
        f"Learn from what is working in {best['label']} while giving attention to {worst['label']}."
        if len(rows) > 1 and worst["sector"] != best["sector"]
        else f"Keep building on the strengths in {best['label']}."
    )
    return summary, key_points, recommendation


def _format_cashflow_answer(ctx: dict[str, Any], selected: list[str]) -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    forecast = intel["forecast_summary"]
    insights = ctx["cashflow_insights"]
    monthly_cf = forecast.get("monthly_cashflow", 0) or 0
    opening = intel["profile"].get("opening_cash_balance", 0) or 0

    summary = (
        f"Average monthly cashflow is about €{monthly_cf:,.0f} on {_sector_scope_label(selected)}."
    )
    if insights.get("negative_months"):
        summary += (
            f" Cash could dip below zero in {', '.join(insights['negative_months'][:3])}"
            f"{' and other months' if len(insights['negative_months']) > 3 else ''} — plan ahead."
        )
    elif insights.get("min_month"):
        summary += (
            f" The tightest month looks like {insights['min_month']} "
            f"(about €{insights['min_balance']:,.0f} running balance)."
        )

    key_points = [
        f"Opening cash: €{opening:,.0f}.",
        f"Average monthly cashflow: €{monthly_cf:,.0f}.",
        f"Cashflow status: {intel['health_score'].get('cashflow', '—')}.",
    ]
    if insights.get("min_month"):
        key_points.append(f"Lowest balance: {insights['min_month']} (€{insights['min_balance']:,.0f}).")
    if insights.get("end_balance") is not None:
        key_points.append(f"Year-end running balance: €{insights['end_balance']:,.0f}.")
    if insights.get("negative_months"):
        key_points.append(f"Months below zero: {', '.join(insights['negative_months'])}.")

    alerts = intel.get("alerts") or []
    if alerts and len(key_points) < 5:
        key_points.append(f"Alert: {alerts[0]}.")

    return summary, key_points[:5], _first_recommendation(intel) or "Plan ahead for low-cash months before taking on new commitments."


def _format_funding_answer(ctx: dict[str, Any]) -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    health = intel["health_score"]
    forecast = intel["forecast_summary"]
    insights = ctx["cashflow_insights"]
    monthly_cf = forecast.get("monthly_cashflow", 0) or 0
    opening = intel["profile"].get("opening_cash_balance", 0) or 0
    debt_pressure = health.get("debt_pressure", "Moderate")
    min_balance = insights.get("min_balance")

    if monthly_cf < 0 or opening < abs(monthly_cf) or (min_balance is not None and min_balance < 0):
        summary = (
            "Cash reserves look tight — you may need extra funding or stronger cash "
            "management before major purchases."
        )
        if insights.get("min_month") and min_balance is not None and min_balance < 0:
            summary += f" The lowest point looks like {insights['min_month']} (about €{min_balance:,.0f})."
        recommendation = "Speak to your bank or adviser about short-term cash support before new debt."
    elif debt_pressure == "High":
        summary = (
            "Debt repayments are already putting pressure on the farm — "
            "additional borrowing should be approached carefully."
        )
        recommendation = "Improve cash reserves or reduce costs before taking on new loans."
    else:
        summary = (
            "You may have some room for funding if needed, but keep a buffer for "
            "feed bills and seasonal dips."
        )
        recommendation = "Only borrow for investments that clearly improve income or reduce costs."

    key_points = [
        f"Debt pressure: {debt_pressure}.",
        f"Monthly cashflow: €{monthly_cf:,.0f}.",
        f"Cash reserves: €{opening:,.0f}.",
        "Funding need applies to the whole farm.",
    ]
    if insights.get("min_month"):
        key_points.append(f"Tightest month: {insights['min_month']} (€{insights['min_balance']:,.0f}).")

    return summary, key_points[:5], recommendation


def _format_general_answer(ctx: dict[str, Any], question: str = "") -> tuple[str, list[str], str]:
    intel = ctx["intel"]
    actions = intel.get("recommended_actions") or []
    weaknesses = intel.get("key_weaknesses") or []
    question_norm = _normalize_question(question)

    if "explain" in question_norm and "simpler" in question_norm:
        health = intel["health_score"]
        forecast = intel["forecast_summary"]
        summary = (
            f"In simple terms, your farm scores {health.get('score', '—')}/100 for financial health. "
            f"You are forecast to make about €{forecast.get('annual_profit', 0):,.0f} profit per year "
            f"with {forecast.get('risk_level', 'Medium')} overall risk."
        )
        key_points = [
            f"Health: {health.get('label', '—')}.",
            f"Cashflow: {health.get('cashflow', '—')}.",
        ]
        if weaknesses:
            key_points.append(f"Main pressure: {weaknesses[0]}.")
        return summary, key_points[:3], _first_recommendation(intel)

    summary = intel.get("plain_summary") or _plain_summary(
        ctx["forecast"],
        intel["health_score"],
        {
            "farm_name": intel.get("farm_name"),
            "opening_cash_balance": intel["profile"].get("opening_cash_balance", 0),
            "loan_repayments": intel["profile"].get("loan_repayments", 0),
        },
    )
    if weaknesses and weaknesses[0].lower() not in summary.lower():
        summary += f" The main pressure area is {weaknesses[0]}."

    key_points = [action["title"] for action in actions[:5]]
    if not key_points:
        key_points = [summary]
    return summary, key_points, _first_recommendation(intel)


def _parse_direction(question: str, default: float = 1.0) -> float:
    q = _normalize_question(question)
    if any(w in q for w in ("decrease", "fall", "drop", "lower", "reduce", "cut")):
        return -1.0
    if any(w in q for w in ("increase", "rise", "higher", "up", "grow", "add")):
        return 1.0
    return default


def _parse_percentage(question: str) -> float | None:
    q = _normalize_question(question)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", q)
    if match:
        return float(match.group(1))
    return None


def _parse_milk_cents(question: str) -> float | None:
    q = _normalize_question(question)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:c/l|cents?|cent(?!\w))", q)
    if match:
        return float(match.group(1)) * _parse_direction(question)
    return None


def _parse_cow_delta(question: str) -> int | None:
    q = _normalize_question(question)
    direction = _parse_direction(question)
    match = re.search(r"(?:add|increase|by)\s*(\d+)\s*(?:more\s*)?cow", q)
    if match:
        return int(match.group(1)) * int(direction)
    match = re.search(r"(\d+)\s*(?:more\s*)?cow", q)
    if match:
        return int(match.group(1)) * int(direction)
    return None


def parse_scenario_inputs(
    question: str,
    intent: str,
    farm_file: str,
    selected: list[str],
) -> dict[str, Any] | None:
    """Map natural-language scenario questions to sandbox input fields."""
    direction = _parse_direction(question)

    if intent == "scenario_milk_price":
        cents = _parse_milk_cents(question)
        if cents is not None:
            return {"milk_price_cents_change": cents}
        pct = _parse_percentage(question)
        if pct is not None:
            return {"milk_price_pct_change": pct * direction}
        return {"milk_price_cents_change": 5 * direction}

    if intent == "scenario_feed_cost":
        pct = _parse_percentage(question) or 10
        return {"feed_pct_change": pct * direction}

    if intent == "scenario_labour_cost":
        pct = _parse_percentage(question) or 8
        return {"labour_pct_change": pct * direction}

    if intent == "scenario_herd_size":
        delta = _parse_cow_delta(question)
        if delta is None:
            return None
        dairy_farm = load_farm_for_analysis(farm_file, ["dairy"])
        current = int(dairy_farm.get("milking_cows") or 0)
        return {"milking_cows": max(0, current + delta)}

    return None


def _deltas_from_sandbox_result(result: dict) -> dict[str, Any]:
    comparison = result.get("comparison") or {}
    base_summary = (result.get("base") or {}).get("forecast_summary") or {}
    scenario_summary = (result.get("scenario") or {}).get("forecast_summary") or {}
    base_kpis = (result.get("base") or {}).get("kpis") or {}
    scenario_kpis = (result.get("scenario") or {}).get("kpis") or {}
    return {
        "revenue_change": comparison.get("revenue_difference"),
        "profit_change": comparison.get("profit_difference"),
        "cashflow_change": round(
            float(scenario_kpis.get("monthly_cashflow") or 0)
            - float(base_kpis.get("monthly_cashflow") or 0),
            0,
        ),
        "margin_change": round(
            float(scenario_summary.get("profit_margin") or 0)
            - float(base_summary.get("profit_margin") or 0),
            1,
        ),
    }


def _estimate_health_after(result: dict, farm_file: str, sectors: list[str]) -> int | None:
    scenario_summary = (result.get("scenario") or {}).get("forecast_summary") or {}
    scenario_kpis = (result.get("scenario") or {}).get("kpis") or {}
    if not scenario_summary:
        return None
    farm = load_farm_for_analysis(farm_file, sectors)
    forecast = {
        **scenario_summary,
        **scenario_kpis,
        "risk_level": (result.get("scenario") or {}).get("risk_level"),
        "feed_cost_ratio": scenario_kpis.get("feed_cost_ratio", 35),
        "monthly_cashflow": scenario_kpis.get("monthly_cashflow", 0),
    }
    return _health_score(forecast, farm).get("score")


def _format_euro(value: float | int | None) -> str:
    if value is None:
        return "—"
    if value > 0:
        return f"+€{value:,.0f}"
    if value < 0:
        return f"-€{abs(value):,.0f}"
    return "€0"


def _handle_scenario(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    dairy_only = intent in ("scenario_milk_price", "scenario_herd_size")
    if dairy_only and "dairy" not in selected:
        return _base_response(
            question,
            intent,
            [],
            selected,
            selected,
            summary=(
                "This scenario only applies to the dairy sector, and dairy is not "
                "in your current sector selection."
            ),
            key_points=[
                "Select Dairy in the sector filter to model this change.",
                "Beef and lamb are not affected by dairy-only scenarios.",
            ],
            recommendation="Add Dairy to your selected sectors to explore this scenario.",
        )

    sandbox_inputs = parse_scenario_inputs(question, intent, farm_file, selected)
    if sandbox_inputs is None:
        return _base_response(
            question,
            intent,
            affected,
            unaffected,
            selected,
            summary="I could not read the scenario details from your question.",
            key_points=[
                "Try including a number, for example: 'add 50 cows' or 'feed costs increase by 10%'.",
            ],
            recommendation="Rephrase your question with a clear percentage or amount.",
        )

    intel = _load_intel(farm_file, selected)
    overall_result = run_scenario_sandbox(farm_file, sandbox_inputs, sectors=selected)
    overall_deltas = _deltas_from_sandbox_result(overall_result)
    comparison = overall_result.get("comparison") or {}

    sector_impact: dict[str, Any] = {}
    for sector in affected:
        sector_result = run_scenario_sandbox(farm_file, sandbox_inputs, sectors=[sector])
        sector_impact[sector] = _deltas_from_sandbox_result(sector_result)

    overall_impact = _empty_overall_impact()
    overall_impact["total_revenue_change"] = overall_deltas["revenue_change"]
    overall_impact["total_profit_change"] = overall_deltas["profit_change"]
    overall_impact["health_score_before"] = intel["health_score"].get("score")
    overall_impact["health_score_after"] = _estimate_health_after(overall_result, farm_file, selected)
    overall_impact["risk_level_before"] = comparison.get("risk_base")
    overall_impact["risk_level_after"] = comparison.get("risk_scenario")

    profit_diff = overall_deltas["profit_change"] or 0
    cf_diff = overall_deltas["cashflow_change"] or 0
    note = _unaffected_note(affected, unaffected)

    if intent == "scenario_milk_price":
        cents = sandbox_inputs.get("milk_price_cents_change")
        pct = sandbox_inputs.get("milk_price_pct_change")
        change_label = f"{cents:+.0f}c/L" if cents else f"{pct:+.1f}%"
        dairy_profit = (sector_impact.get("dairy") or {}).get("profit_change", profit_diff) or 0
        summary = (
            f"If milk price changes by {change_label}, dairy profit would change by "
            f"about {_format_euro(dairy_profit)}. "
            f"Whole-farm profit would change by about {_format_euro(profit_diff)}."
        )
        if note:
            summary = f"{summary} {note}"
        key_points = [
            f"Dairy profit change: {_format_euro(dairy_profit)}.",
            f"Whole-farm profit change: {_format_euro(profit_diff)}.",
            f"Monthly cashflow change: {_format_euro(cf_diff)}.",
        ]
        if overall_impact["health_score_before"] is not None and overall_impact["health_score_after"] is not None:
            key_points.append(
                f"Health score: {overall_impact['health_score_before']} → {overall_impact['health_score_after']}."
            )
        if overall_impact["risk_level_before"] and overall_impact["risk_level_after"]:
            key_points.append(
                f"Risk level: {overall_impact['risk_level_before']} → {overall_impact['risk_level_after']}."
            )
        recommendation = (
            overall_result.get("recommendations") or [{}]
        )[0].get("title", "Review dairy cashflow before committing to new costs.")

    elif intent == "scenario_feed_cost":
        labels = ", ".join(_sector_label(s) for s in affected)
        summary = (
            f"If feed costs change as modelled, whole-farm profit would change by "
            f"about {_format_euro(profit_diff)} across {labels}."
        )
        key_points = [
            f"Whole-farm profit change: {_format_euro(profit_diff)}.",
            f"Monthly cashflow change: {_format_euro(cf_diff)}.",
        ]
        for sector, impact in sector_impact.items():
            key_points.append(
                f"{_sector_label(sector)} profit change: {_format_euro(impact.get('profit_change'))}."
            )
        recommendation = (
            overall_result.get("recommendations") or [{}]
        )[0].get("title", "Compare feed quotes and ration efficiency before accepting higher bills.")

    elif intent == "scenario_labour_cost":
        labels = ", ".join(_sector_label(s) for s in affected)
        summary = (
            f"If labour costs change as modelled, whole-farm profit would change by "
            f"about {_format_euro(profit_diff)} across {labels}."
        )
        key_points = [
            f"Whole-farm profit change: {_format_euro(profit_diff)}.",
            f"Monthly cashflow change: {_format_euro(cf_diff)}.",
        ]
        for sector, impact in sector_impact.items():
            key_points.append(
                f"{_sector_label(sector)} profit change: {_format_euro(impact.get('profit_change'))}."
            )
        recommendation = (
            overall_result.get("recommendations") or [{}]
        )[0].get("title", "Review staffing plans before labour costs rise further.")

    elif intent == "scenario_herd_size":
        dairy_profit = (sector_impact.get("dairy") or {}).get("profit_change", profit_diff) or 0
        cows = sandbox_inputs.get("milking_cows")
        summary = (
            f"Changing the dairy herd to {cows} cows would change dairy profit by "
            f"about {_format_euro(dairy_profit)} and whole-farm profit by about {_format_euro(profit_diff)}."
        )
        if note:
            summary = f"{summary} {note}"
        key_points = [
            f"Target herd size: {cows} cows.",
            f"Dairy profit change: {_format_euro(dairy_profit)}.",
            f"Whole-farm profit change: {_format_euro(profit_diff)}.",
            f"Monthly cashflow change: {_format_euro(cf_diff)}.",
        ]
        recommendation = (
            overall_result.get("recommendations") or [{}]
        )[0].get("title", "Confirm feed, labour, and housing capacity before expanding the herd.")

    else:
        summary = overall_result.get("summary") or "Scenario analysis complete."
        key_points = [summary]
        recommendation = "Review the impact on cashflow before making changes."

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points[:5],
        recommendation=recommendation,
        sector_impact=sector_impact,
        overall_impact=overall_impact,
        metrics={
            "profit_change": profit_diff,
            "cashflow_change": cf_diff,
            "health_score": overall_impact["health_score_after"] or overall_impact["health_score_before"],
            "risk_level": overall_impact["risk_level_after"] or overall_impact["risk_level_before"],
        },
    )


def _handle_scenario_milk_price(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    return _handle_scenario(question, farm_file, selected, affected, unaffected, intent)


def _handle_scenario_feed_cost(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    return _handle_scenario(question, farm_file, selected, affected, unaffected, intent)


def _handle_scenario_labour_cost(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    return _handle_scenario(question, farm_file, selected, affected, unaffected, intent)


def _handle_scenario_herd_size(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    return _handle_scenario(question, farm_file, selected, affected, unaffected, intent)


def _handle_health_score(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    intel = ctx["intel"]
    summary, key_points, recommendation = _format_health_answer(ctx)
    overall = _empty_overall_impact()
    overall["health_score_before"] = intel["health_score"].get("score")
    overall["risk_level_before"] = intel["forecast_summary"].get("risk_level")

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        overall_impact=overall,
        metrics={
            "health_score": intel["health_score"].get("score"),
            "risk_level": intel["forecast_summary"].get("risk_level"),
            "profit_change": None,
            "cashflow_change": None,
        },
    )


def _handle_strengths(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    summary, key_points, recommendation = _format_strengths_answer(ctx, selected)
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        metrics={"health_score": ctx["intel"]["health_score"].get("score")},
    )


def _handle_risks(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    summary, key_points, recommendation = _format_risks_answer(ctx)
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        metrics={"risk_level": ctx["intel"]["forecast_summary"].get("risk_level")},
    )


def _handle_profitability(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    intel = ctx["intel"]
    forecast = intel["forecast_summary"]
    summary, key_points, recommendation = _format_profitability_answer(ctx, question, farm_file, selected)

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points[:5],
        recommendation=recommendation,
        metrics={
            "health_score": intel["health_score"].get("score"),
            "profit_change": None,
            "cashflow_change": forecast.get("monthly_cashflow"),
            "risk_level": forecast.get("risk_level"),
        },
    )


def _handle_sector_comparison(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    filtered = get_selected_sector_data(farm_file, selected)
    rows = calculate_sector_performance(filtered)
    if not rows:
        return _base_response(
            question,
            intent,
            affected,
            unaffected,
            selected,
            summary="No sector performance data is available for your current selection.",
            key_points=["Check that at least one sector is selected."],
            recommendation="Select the sectors you want to compare in the header.",
        )

    summary, key_points, recommendation = _format_sector_comparison_answer(rows)
    ctx = _load_advisor_context(farm_file, selected)

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        metrics={
            "health_score": ctx["intel"]["health_score"].get("score"),
            "risk_level": ctx["intel"]["forecast_summary"].get("risk_level"),
        },
    )


def _handle_cashflow_forecast(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    intel = ctx["intel"]
    forecast = intel["forecast_summary"]
    summary, key_points, recommendation = _format_cashflow_answer(ctx, selected)

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        metrics={
            "cashflow_change": forecast.get("monthly_cashflow"),
            "risk_level": forecast.get("risk_level"),
            "health_score": intel["health_score"].get("score"),
        },
    )


def _handle_funding_need(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    intel = ctx["intel"]
    forecast = intel["forecast_summary"]
    summary, key_points, recommendation = _format_funding_answer(ctx)

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        metrics={
            "health_score": intel["health_score"].get("score"),
            "cashflow_change": forecast.get("monthly_cashflow"),
            "risk_level": forecast.get("risk_level"),
        },
    )


def _handle_general_recommendation(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    ctx = _load_advisor_context(farm_file, selected)
    intel = ctx["intel"]
    summary, key_points, recommendation = _format_general_answer(ctx, question)
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        selected,
        summary=summary,
        key_points=key_points,
        recommendation=recommendation,
        metrics={
            "health_score": intel["health_score"].get("score"),
            "risk_level": intel["forecast_summary"].get("risk_level"),
        },
    )


_HANDLERS: dict[str, Handler] = {
    "scenario_milk_price": _handle_scenario_milk_price,
    "scenario_feed_cost": _handle_scenario_feed_cost,
    "scenario_labour_cost": _handle_scenario_labour_cost,
    "scenario_herd_size": _handle_scenario_herd_size,
    "health_score": _handle_health_score,
    "strengths": _handle_strengths,
    "risks": _handle_risks,
    "profitability": _handle_profitability,
    "sector_comparison": _handle_sector_comparison,
    "cashflow_forecast": _handle_cashflow_forecast,
    "funding_need": _handle_funding_need,
    "general_recommendation": _handle_general_recommendation,
}


def ask_farm_intelligence(
    question: str,
    farm_file: str | None = None,
    sectors: list[str] | None = None,
) -> dict[str, Any]:
    """Route a farmer question to the appropriate analysis handler."""
    resolved_file = resolve_farm_file(farm_file)
    selected = resolve_sectors(sectors, resolved_file)
    intent = detect_intent(question)
    affected, unaffected = resolve_affected_sectors(intent, selected)
    handler = _HANDLERS.get(intent, _handle_general_recommendation)
    return handler(question, resolved_file, selected, affected, unaffected, intent)
