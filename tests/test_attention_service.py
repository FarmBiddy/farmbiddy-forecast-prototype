"""Tests for the unified "Needs Your Attention" feed (P1.1).

`build_needs_attention` is a pure combiner over already-computed alert/
warning/variance data, so these tests exercise it directly with small
hand-built inputs rather than a full farm dataset.
"""

from __future__ import annotations

from services.attention_service import build_needs_attention


def _forecast_alert(**overrides):
    base = {
        "message": "Cash-flow warning in month 4.",
        "severity": "high",
        "priority": 2,
        "what": "Future months show a negative cash balance",
        "when": "Month 4",
        "cause": "Projected outgoings exceed projected income in the affected month(s).",
        "review": "Plan ahead for the shortfall.",
    }
    base.update(overrides)
    return base


def _dq_warning(**overrides):
    base = {
        "type": "outdated_data",
        "area": "Farm Data",
        "severity": "medium",
        "message": "Farm records were last updated 6 months ago.",
    }
    base.update(overrides)
    return base


def _category_row(**overrides):
    base = {
        "record_type": "expense",
        "category_id": "feed",
        "label": "Feed",
        "status": "above_budget",
        "budget_total": 1000.0,
        "actual_total": 1200.0,
        "difference": 200.0,
        "months_with_budget": 1,
        "months_in_window": 12,
        "summary": "Feed is €200 above budget.",
    }
    base.update(overrides)
    return base


def test_empty_inputs_return_empty_list():
    assert build_needs_attention(None, None, None) == []
    assert build_needs_attention([], [], {"top_contributors": []}) == []


def test_info_severity_forecast_alert_is_excluded():
    alerts = [{"message": "No critical alerts.", "severity": "info", "priority": 99, "what": "x", "when": "x", "cause": "x", "review": "x"}]
    assert build_needs_attention(alerts, None, None) == []


def test_forecast_alert_passes_through_with_what_when_why_review():
    alerts = [_forecast_alert()]
    result = build_needs_attention(alerts, None, None)
    assert len(result) == 1
    item = result[0]
    assert item["source"] == "forecast"
    assert item["what"] == "Future months show a negative cash balance"
    assert item["when"] == "Month 4"
    assert item["why"] == "Projected outgoings exceed projected income in the affected month(s)."
    assert item["review"] == "Plan ahead for the shortfall."
    assert item["severity"] == "high"


def test_data_quality_warning_is_converted_with_why_and_review():
    result = build_needs_attention(None, [_dq_warning()], None)
    assert len(result) == 1
    item = result[0]
    assert item["source"] == "data_quality"
    assert item["type"] == "outdated_data"
    assert item["what"] == "Farm Data: records are out of date"
    assert item["why"] == "Farm records were last updated 6 months ago."
    assert "Update Farm Data" in item["review"]
    assert item["severity"] == "medium"


def test_unknown_data_quality_type_still_gets_a_generic_what_and_review():
    result = build_needs_attention(None, [_dq_warning(type="some_new_check")], None)
    assert result[0]["what"] == "Farm Data: record is missing or incomplete"
    assert result[0]["review"]


def test_expense_above_budget_category_is_included():
    category_result = {"period": {"label": "Trailing 12 Months"}, "top_contributors": [_category_row()]}
    result = build_needs_attention(None, None, category_result)
    assert len(result) == 1
    item = result[0]
    assert item["source"] == "budget_category"
    assert item["type"] == "category_above_budget"
    assert item["what"] == "Feed is €200 above budget."
    assert item["when"] == "Trailing 12 Months"
    assert "Feed" in item["why"]
    assert "Budget by Category" in item["review"]


def test_income_behind_budget_category_is_included():
    row = _category_row(record_type="income", category_id="milk", label="Milk", status="behind", summary="Milk is €300 behind budget.")
    category_result = {"period": {"label": "Trailing 12 Months"}, "top_contributors": [row]}
    result = build_needs_attention(None, None, category_result)
    assert len(result) == 1
    assert result[0]["type"] == "category_behind"


def test_good_news_category_directions_are_excluded():
    # Expense running under budget, and income running ahead of budget, are
    # both "good news" and must not surface as something to act on.
    below = _category_row(status="below_budget", summary="Feed is €50 below budget.")
    ahead = _category_row(record_type="income", category_id="milk", label="Milk", status="ahead", summary="Milk is €80 ahead of budget.")
    on_budget = _category_row(status="on_budget", summary="Feed is on budget.")
    no_budget = _category_row(status="no_budget_set", summary="No budget set for Feed yet.")
    category_result = {
        "period": {"label": "Trailing 12 Months"},
        "top_contributors": [below, ahead, on_budget, no_budget],
    }
    assert build_needs_attention(None, None, category_result) == []


def test_combined_sources_are_sorted_by_severity_then_priority():
    alerts = [
        _forecast_alert(message="low margin", severity="medium", priority=4, what="Low profit margin"),
        _forecast_alert(message="cash warning", severity="high", priority=1, what="Cash warning"),
    ]
    dq = [_dq_warning(severity="low", area="Debt Register")]
    category_result = {"period": {"label": "Trailing 12 Months"}, "top_contributors": [_category_row()]}

    result = build_needs_attention(alerts, dq, category_result)
    severities = [item["severity"] for item in result]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2, "info": 3}[s])
    assert result[0]["what"] == "Cash warning"


def test_limit_truncates_the_combined_list():
    alerts = [_forecast_alert(message=f"alert {i}", what=f"Alert {i}", priority=5) for i in range(5)]
    dq = [_dq_warning(area=f"Area {i}") for i in range(5)]
    result = build_needs_attention(alerts, dq, None, limit=3)
    assert len(result) == 3
