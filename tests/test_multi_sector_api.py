"""API smoke tests for multi-sector farm endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_farmer_sectors_endpoint():
    response = client.get("/api/farmer/sectors?farm_file=multi_sector_farm.json")
    assert response.status_code == 200
    data = response.json()
    assert len(data["available_sectors"]) == 3
    assert data["selected_sectors"] == ["dairy", "beef", "lamb"]


def test_dashboard_with_beef_only():
    response = client.get(
        "/api/farmer/dashboard?farm_file=multi_sector_farm.json&sectors=beef"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["selected_sectors"] == ["beef"]
    kpi_ids = [k["id"] for k in data["executive_kpis"]]
    assert len(kpi_ids) == 6
    assert "revenue" in kpi_ids
    assert "milk_price" not in kpi_ids


def test_run_analysis_all_sectors():
    response = client.post(
        "/api/farmer/run-analysis",
        json={
            "farm_file": "multi_sector_farm.json",
            "sectors": ["dairy", "beef", "lamb"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["forecast_summary"]["annual_profit"] > 0
    assert len(data["executive_kpis"]) == 6
    assert len(data["health_snapshot"]) == 6
    assert len(data["sector_performance"]) == 3
    assert len(data["overview_chart"]) >= 12
    assert data["overview_header"]["status_label"] == "Combined Overview"
    assert len(data["debt_register"]) == 2
    for loan in data["debt_register"]:
        assert "outstanding_balance" in loan
        assert "years_remaining" in loan
    # Phase 6: month-by-month early cash-flow warnings should surface alongside
    # the legacy annual-level alerts when the farm's monthly forecast dips negative.
    alert_messages = " | ".join(a["message"] for a in data["alerts"])
    assert "Cash-flow warning" in alert_messages or "Increasing overdraft use" in alert_messages
    # Phase 7: the dashboard's health score must be the same canonical number
    # Farm Intelligence shows — the two surfaces should never disagree.
    assert "health_score" in data
    intelligence = client.get(
        "/api/farmer/financial-intelligence?farm_file=multi_sector_farm.json&sectors=dairy,beef,lamb"
    ).json()
    assert data["health_score"] == intelligence["health_score"]
    # Phase 8: every dashboard alert carries the richer what/when/cause/review fields.
    for alert in data["alerts"]:
        assert set(("what", "when", "cause", "review")) <= set(alert.keys())
        assert alert["what"] and alert["when"] and alert["cause"] and alert["review"]
    # Phase 9: the sample dataset is stale (last month is well over 2 months
    # old) and flagged as sample data, so both warnings should surface.
    assert "data_quality_warnings" in data
    warning_types = {w["type"] for w in data["data_quality_warnings"]}
    assert "outdated_data" in warning_types
    assert "sample_data" in warning_types
    for warning in data["data_quality_warnings"]:
        assert set(("type", "area", "severity", "message")) <= set(warning.keys())
    # P1.1: "Needs Your Attention" consolidates forecast alerts, data-quality
    # warnings, and category-budget variances into one prioritised list, each
    # with a consistent what/when/why/review shape.
    assert "needs_attention" in data
    assert len(data["needs_attention"]) > 0
    sources = {item["source"] for item in data["needs_attention"]}
    assert "forecast" in sources
    assert "data_quality" in sources
    for item in data["needs_attention"]:
        assert set(("source", "what", "when", "why", "review", "severity")) <= set(item.keys())
        assert item["what"] and item["review"]
        assert item["severity"] != "info"
    # The Overview's headline "Needs Your Attention" card must reflect the
    # same top-priority item as the consolidated feed, not a stale forecast-
    # only concern.
    assert data["overview_summary"]["main_financial_concern"] == data["needs_attention"][0]["what"]
    assert data["overview_summary"]["recommended_next_action"] == data["needs_attention"][0]["review"]


def test_historical_data_endpoint():
    response = client.get(
        "/api/farmer/historical-data?farm_file=multi_sector_farm.json&sectors=dairy"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["selected_sectors"] == ["dairy"]
    assert len(data["sectors"]) == 1


def test_cashflow_budget_endpoint():
    response = client.get(
        "/api/farmer/cashflow-budget?farm_file=multi_sector_farm.json&sectors=dairy,beef,lamb"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["entries"]) == 24
    assert "deficit_months" in data
    assert "behind_budget_months" in data
    assert "long_term_deficit_months" in data
    assert "short_term_deficit_months" in data
    for entry in data["entries"]:
        assert entry["cashflow_status"] in ("deficit", "surplus", "breakeven")
        assert entry["budget_status"] in ("ahead", "behind", "on_budget")
        assert "classification" in entry
        assert "classification_reason" in entry
        # Phase 10: each month names the calendar period it covers.
        assert entry["period_info"]["period_type"] == "Historical Actual"


def test_cashflow_actions_endpoint_defaults():
    response = client.get(
        "/api/farmer/cashflow-actions?farm_file=multi_sector_farm.json&sectors=dairy,beef,lamb"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "base_lowest_balance" in data
    assert "base_deficit_months" in data
    # Phase 10: a scenario-testing result is not a calendar-anchored figure.
    assert data["period"]["period_type"] == "Scenario Result"
    assert len(data["results"]) == 5
    action_names = {r["action"] for r in data["results"]}
    assert action_names == {
        "bring_forward_sales",
        "defer_purchases",
        "adjust_loan_timing",
        "match_payments_to_surplus",
        "use_short_term_credit",
    }
    for result in data["results"]:
        assert isinstance(result["description"], str) and result["description"]
        assert "lowest_balance_scenario" in result
        assert "deficit_months_scenario" in result


def test_cashflow_action_endpoint_single_action_with_explicit_inputs():
    response = client.post(
        "/api/farmer/cashflow-action",
        json={
            "farm_file": "multi_sector_farm.json",
            "sectors": ["dairy", "beef", "lamb"],
            "action": "defer_purchases",
            "from_month": 4,
            "to_month": 6,
            "amount": 5000,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "defer_purchases"
    assert isinstance(data["description"], str) and data["description"]
    assert "lowest_balance_base" in data
    assert "lowest_balance_scenario" in data
    assert "improvement" in data
    assert data["period"]["period_type"] == "Scenario Result"


def test_cashflow_action_endpoint_unknown_action_returns_400():
    response = client.post(
        "/api/farmer/cashflow-action",
        json={
            "farm_file": "multi_sector_farm.json",
            "action": "not_a_real_action",
        },
    )
    assert response.status_code == 400
