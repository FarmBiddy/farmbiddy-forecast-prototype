"""
Farm Intelligence advisor — rule-based question routing.

Phase 3: intent detection and structured responses. Scenario numbers and full
sector-aware sandbox integration are completed in Phases 5–6.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from services.dashboard_summary import calculate_sector_performance, get_selected_sector_data
from services.farmer_dashboard_service import resolve_farm_file, resolve_sectors
from services.financial_intelligence_service import get_financial_intelligence

Handler = Callable[..., dict[str, Any]]


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def detect_intent(question: str) -> str:
    """Rule-based intent detection — first match wins (most specific patterns first)."""
    q = _normalize_question(question)
    if not q:
        return "general_recommendation"

    milk_scenario = (
        "milk price" in q
        or "c/l" in q
        or re.search(r"\d+\s*c(?:ent)?s?", q)
        or ("milk" in q and any(w in q for w in ("increase", "decrease", "rise", "fall", "drop", "what if", "what happens")))
    )
    if milk_scenario and "feed" not in q:
        return "scenario_milk_price"

    if "feed" in q and any(
        w in q for w in ("%", "percent", "increase", "decrease", "rise", "fall", "what if", "what happens", "cost")
    ):
        return "scenario_feed_cost"

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


def _base_response(
    question: str,
    intent: str,
    affected: list[str],
    unaffected: list[str],
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
        "sector_impact": sector_impact if sector_impact is not None else _sector_impact_for(affected),
        "overall_impact": overall_impact if overall_impact is not None else _empty_overall_impact(),
        "summary": summary,
        "key_points": key_points,
        "recommendation": recommendation,
        "metrics": metrics or {},
    }


def _load_intel(farm_file: str, selected: list[str]) -> dict[str, Any]:
    return get_financial_intelligence(farm_file, sectors=selected)


def _handle_scenario_milk_price(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    if "dairy" not in selected:
        return _base_response(
            question,
            intent,
            [],
            selected,
            summary=(
                "Milk price changes only affect the dairy sector, and dairy is not "
                "in your current sector selection."
            ),
            key_points=[
                "Select Dairy in the sector filter to model milk price changes.",
                "Beef and lamb prices are separate from dairy milk price.",
            ],
            recommendation="Add Dairy to your selected sectors if you want to explore milk price scenarios.",
        )

    note = _unaffected_note(affected, unaffected)
    summary = (
        "This is a dairy-only scenario. A milk price change would directly affect "
        "dairy revenue and profit."
    )
    if note:
        summary = f"{summary} {note}"

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=[
            "Direct impact: Dairy sector only.",
            "Overall farm totals will move by the dairy change amount.",
            "Detailed euro estimates will be calculated in the next implementation phase.",
        ],
        recommendation="Review dairy cashflow after any milk price change before committing to new costs.",
        sector_impact=_sector_impact_for(affected),
    )


def _handle_scenario_feed_cost(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    labels = ", ".join(_sector_label(s) for s in affected) or "your selected sectors"
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=(
            f"A feed cost change would affect {labels} because feed is shared "
            "across the sectors you have selected."
        ),
        key_points=[
            f"Direct impact: {labels}.",
            "Overall farm profit and cashflow would reflect the combined feed change.",
            "Detailed percentage and euro estimates will be calculated in the next phase.",
        ],
        recommendation="Compare feed quotes and ration efficiency before accepting higher feed bills.",
        sector_impact=_sector_impact_for(affected),
    )


def _handle_health_score(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    intel = _load_intel(farm_file, selected)
    health = intel["health_score"]
    forecast = intel["forecast_summary"]
    overall = _empty_overall_impact()
    overall["health_score_before"] = health.get("score")
    overall["risk_level_before"] = forecast.get("risk_level")

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=(
            f"Your farm health score is {health.get('score', '—')}/100 ({health.get('label', '—')}). "
            f"Profitability is {health.get('profitability', '—').lower()}, cashflow is "
            f"{health.get('cashflow', '—').lower()}, and overall risk is {forecast.get('risk_level', '—')}."
        ),
        key_points=[
            f"Profitability: {health.get('profitability', '—')}.",
            f"Cashflow: {health.get('cashflow', '—')}.",
            f"Feed pressure: {health.get('feed_pressure', '—')}.",
            f"Debt pressure: {health.get('debt_pressure', '—')}.",
        ],
        recommendation=intel.get("recommended_actions", [{}])[0].get(
            "title",
            "Keep monitoring cash and costs each month.",
        ),
        overall_impact=overall,
        metrics={
            "health_score": health.get("score"),
            "risk_level": forecast.get("risk_level"),
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
    intel = _load_intel(farm_file, selected)
    strengths = intel.get("key_strengths") or ["No major strengths flagged yet — keep building reserves."]
    summary = "Your main financial strengths right now: " + "; ".join(strengths[:3]) + "."
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=strengths[:5],
        recommendation="Build on these strengths while keeping costs under control.",
        metrics={"health_score": intel["health_score"].get("score")},
    )


def _handle_risks(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    intel = _load_intel(farm_file, selected)
    risks = intel.get("biggest_risks") or []
    if risks:
        summary = "Your biggest financial risks: " + "; ".join(
            f"{r.get('driver', 'Risk')} ({r.get('severity', 'Medium')})" for r in risks[:3]
        ) + "."
        key_points = [
            f"{r.get('driver', 'Risk')} — {r.get('severity', 'Medium')}"
            + (f": {r.get('commentary')}" if r.get("commentary") else "")
            for r in risks[:5]
        ]
    else:
        summary = f"No critical risks flagged. Overall risk level is {intel['forecast_summary'].get('risk_level', 'Medium')}."
        key_points = [summary]

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=key_points,
        recommendation="Address the highest-severity risk first and keep a cash buffer.",
        metrics={"risk_level": intel["forecast_summary"].get("risk_level")},
    )


def _handle_profitability(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    intel = _load_intel(farm_file, selected)
    forecast = intel["forecast_summary"]
    profit = forecast.get("annual_profit", 0) or 0
    margin = forecast.get("profit_margin", 0) or 0

    if profit < 0:
        summary = (
            f"On current figures the farm may lose about €{abs(profit):,.0f} per year "
            f"with a {margin:.1f}% margin — review costs and income urgently."
        )
        recommendation = "Focus on the largest cost lines and cashflow before new spending."
    else:
        summary = (
            f"The farm is forecast to make about €{profit:,.0f} profit per year "
            f"with a {margin:.1f}% margin on your selected sectors."
        )
        recommendation = "Protect margin by monitoring feed and keeping reserves for seasonal dips."

    weaknesses = intel.get("key_weaknesses") or []
    key_points = [
        f"Annual profit: €{profit:,.0f}.",
        f"Profit margin: {margin:.1f}%.",
        f"Monthly cashflow: €{forecast.get('monthly_cashflow', 0):,.0f}.",
    ]
    if weaknesses:
        key_points.append(f"Pressure area: {weaknesses[0]}")

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
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
            summary="No sector performance data is available for your current selection.",
            key_points=["Check that at least one sector is selected."],
            recommendation="Select the sectors you want to compare in the header.",
        )

    best = max(rows, key=lambda r: r.get("profit", 0))
    summary = (
        f"{best['label']} is performing best with about €{best['profit']:,.0f} profit "
        f"and a {best['margin_pct']:.1f}% margin over the last 12 months."
    )
    key_points = [
        f"{row['label']}: €{row['profit']:,.0f} profit, {row['margin_pct']:.1f}% margin ({row['status']})"
        for row in rows
    ]

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=key_points,
        recommendation=f"Learn from what is working in {best['label']} without neglecting weaker sectors.",
        metrics={"health_score": None, "risk_level": None},
    )


def _handle_cashflow_forecast(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    intel = _load_intel(farm_file, selected)
    forecast = intel["forecast_summary"]
    monthly_cf = forecast.get("monthly_cashflow", 0) or 0
    summary = (
        f"Average monthly cashflow is about €{monthly_cf:,.0f} on your selected sectors. "
        "Seasonal dips are common — watch months where bills cluster."
    )
    key_points = [
        f"Average monthly cashflow: €{monthly_cf:,.0f}.",
        f"Opening cash balance: €{intel['profile'].get('opening_cash_balance', 0):,.0f}.",
        f"Cashflow status: {intel['health_score'].get('cashflow', '—')}.",
        "A month-by-month 12-month view will be added in the next phase.",
    ]
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=key_points,
        recommendation="Plan ahead for low-cash months before taking on new commitments.",
        metrics={"cashflow_change": monthly_cf, "risk_level": forecast.get("risk_level")},
    )


def _handle_funding_need(
    question: str,
    farm_file: str,
    selected: list[str],
    affected: list[str],
    unaffected: list[str],
    intent: str,
) -> dict[str, Any]:
    intel = _load_intel(farm_file, selected)
    health = intel["health_score"]
    forecast = intel["forecast_summary"]
    monthly_cf = forecast.get("monthly_cashflow", 0) or 0
    opening = intel["profile"].get("opening_cash_balance", 0) or 0
    debt_pressure = health.get("debt_pressure", "Moderate")

    if monthly_cf < 0 or opening < abs(monthly_cf):
        summary = (
            "Cash reserves look tight — you may need extra funding or stronger cash "
            "management before major purchases."
        )
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

    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=[
            f"Debt pressure: {debt_pressure}.",
            f"Monthly cashflow: €{monthly_cf:,.0f}.",
            f"Cash reserves: €{opening:,.0f}.",
            _unaffected_note(affected, unaffected) or "Funding need applies to the whole farm.",
        ],
        recommendation=recommendation,
        metrics={
            "health_score": health.get("score"),
            "cashflow_change": monthly_cf,
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
    intel = _load_intel(farm_file, selected)
    actions = intel.get("recommended_actions") or []
    top = actions[0]["title"] if actions else "Review monthly cashflow and costs."
    summary = intel.get("plain_summary") or intel.get("advisor_headline") or "Here is a summary of your farm finances."
    key_points = [a["title"] for a in actions[:5]] or [summary]
    return _base_response(
        question,
        intent,
        affected,
        unaffected,
        summary=summary,
        key_points=key_points,
        recommendation=top,
        metrics={"health_score": intel["health_score"].get("score"), "risk_level": intel["forecast_summary"].get("risk_level")},
    )


_HANDLERS: dict[str, Handler] = {
    "scenario_milk_price": _handle_scenario_milk_price,
    "scenario_feed_cost": _handle_scenario_feed_cost,
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
