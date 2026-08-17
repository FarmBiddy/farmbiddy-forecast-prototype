"""Unified "Needs Your Attention" feed (P1.1).

Consolidates every farmer-facing actionable warning already produced
elsewhere in the app into one prioritised list with a consistent
WHAT / WHEN / WHY / WHAT TO REVIEW shape:

* forecast/cash-flow alerts        -> services.dashboard_summary.generate_dashboard_alerts
* data-quality warnings            -> forecast_engine.data_quality.build_data_quality_warnings
* category-level budget variances  -> services.category_variance_service.build_category_budget_vs_actual

This module derives no new financial figures of its own - it only
re-presents findings already computed and tested elsewhere. Nothing is
fabricated: a category with no budget set never becomes an alert, a farm
with no data-quality issues contributes nothing, "on budget" categories
are silent, and a farm with a clean forecast contributes nothing from
that source either.

Deliberately excluded: the "good news" direction of a category variance
(income running ahead of budget, an expense category running under
budget). Those remain visible in Budget by Category, but they are not
something the farmer needs to act on, so they do not belong in a feed
called "Needs Your Attention".
"""

from __future__ import annotations

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}
SEVERITY_PRIORITY_FALLBACK = {"high": 1, "medium": 5, "low": 8, "info": 99}

# Mirrors the plain-language reasoning already produced by each
# `forecast_engine.data_quality` check (Phase 9) - reshaped into the same
# what/review fields the forecast alerts use, rather than inventing a
# second explanation path.
DATA_QUALITY_DETAILS = {
    "missing_data": {
        "what": "is missing from your records",
        "review": "Fill in the missing field in Farm Data so this figure reflects your own numbers.",
    },
    "outdated_data": {
        "what": "records are out of date",
        "review": "Update Farm Data with your most recent month's figures.",
    },
    "incomplete_assumptions": {
        "what": "is relying on an estimate",
        "review": "Add the missing loan detail under Loans & Finance for an accurate figure.",
    },
    "reconciliation": {
        "what": "figures don't add up",
        "review": "Re-run the analysis; if the mismatch persists, check the underlying monthly records in Farm Data.",
    },
    "sample_data": {
        "what": "is still using sample data",
        "review": "Replace the sample data with your own farm's records in Farm Data.",
    },
}
_DEFAULT_DQ_WHAT = "record is missing or incomplete"

# Statuses from category_variance_service that represent a genuine
# "needs attention" direction, mapped to a short cause phrase. The
# opposite ("good news") direction for each record type is left out on
# purpose - see module docstring.
_CONCERNING_CATEGORY_STATUSES = {
    ("expense", "above_budget"): "spending more in this category than the budget you set for it.",
    ("income", "behind"): "bringing in less than the budget you set for it.",
}


def _forecast_alert_to_attention(alert: dict) -> dict | None:
    if alert.get("severity") == "info":
        return None
    return {
        "source": "forecast",
        "type": "forecast_alert",
        "what": alert.get("what") or alert.get("message", ""),
        "when": alert.get("when", ""),
        "why": alert.get("cause", ""),
        "review": alert.get("review", ""),
        "message": alert.get("message", ""),
        "severity": alert.get("severity", "medium"),
        "priority": alert.get("priority", SEVERITY_PRIORITY_FALLBACK.get(alert.get("severity", "medium"), 5)),
    }


def _data_quality_to_attention(warning: dict) -> dict:
    details = DATA_QUALITY_DETAILS.get(warning.get("type"), {})
    severity = warning.get("severity") if warning.get("severity") in SEVERITY_RANK else "medium"
    area = warning.get("area") or "Data quality"
    return {
        "source": "data_quality",
        "type": warning.get("type", "data_quality"),
        "what": f"{area}: {details.get('what', _DEFAULT_DQ_WHAT)}",
        "when": "Now",
        "why": warning.get("message", ""),
        "review": details.get("review", "Review this figure in Farm Data."),
        "message": warning.get("message", ""),
        "severity": severity,
        "priority": SEVERITY_PRIORITY_FALLBACK.get(severity, 5),
    }


def _category_row_to_attention(row: dict, period_label: str) -> dict | None:
    record_type = row.get("record_type")
    status = row.get("status")
    cause = _CONCERNING_CATEGORY_STATUSES.get((record_type, status))
    if cause is None:
        return None
    label = row.get("label", "This category")
    return {
        "source": "budget_category",
        "type": f"category_{status}",
        "what": row.get("summary", label),
        "when": period_label,
        "why": f"{label} is {cause}",
        "review": f"Review {label} entries under Income & Expenses, or adjust its budget under Budget by Category.",
        "message": row.get("summary", ""),
        "severity": "medium",
        "priority": 4,
    }


def build_needs_attention(
    alerts: list[dict] | None,
    data_quality_warnings: list[dict] | None,
    category_budget_result: dict | None,
    limit: int = 12,
) -> list[dict]:
    """Build the unified, prioritised "Needs Your Attention" list.

    Each item has the shape: source, type, what, when, why, review,
    message, severity, priority. Sorted by severity first, then by the
    same fine-grained priority the forecast alerts already use so a
    "negative profit" alert always outranks a "low feed cost" one
    regardless of which source produced it.
    """
    items: list[dict] = []

    for alert in alerts or []:
        converted = _forecast_alert_to_attention(alert)
        if converted:
            items.append(converted)

    for warning in data_quality_warnings or []:
        items.append(_data_quality_to_attention(warning))

    if category_budget_result:
        period_label = (category_budget_result.get("period") or {}).get("label") or "the current period"
        for row in category_budget_result.get("top_contributors") or []:
            converted = _category_row_to_attention(row, period_label)
            if converted:
                items.append(converted)

    items.sort(key=lambda a: (SEVERITY_RANK.get(a.get("severity"), 2), a.get("priority", 5)))
    return items[:limit]
