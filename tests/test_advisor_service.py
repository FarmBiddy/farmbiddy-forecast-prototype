"""Unit and API tests for the Farm Intelligence advisor router (Phase 3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from services.advisor_service import (
    ask_farm_intelligence,
    detect_intent,
    resolve_affected_sectors,
)

client = TestClient(app)

REQUIRED_RESPONSE_KEYS = {
    "success",
    "question",
    "intent",
    "affected_sectors",
    "unaffected_sectors",
    "sector_impact",
    "overall_impact",
    "summary",
    "key_points",
    "recommendation",
    "metrics",
}


def test_detect_intent_examples():
    assert detect_intent("What happens if milk price increases by 5c/L?") == "scenario_milk_price"
    assert detect_intent("What happens if feed costs increase by 10%?") == "scenario_feed_cost"
    assert detect_intent("How healthy is my business?") == "health_score"
    assert detect_intent("What are my key strengths?") == "strengths"
    assert detect_intent("What are my biggest financial risks?") == "risks"
    assert detect_intent("Which sector is performing best?") == "sector_comparison"
    assert detect_intent("Will I need additional funding?") == "funding_need"
    assert detect_intent("What will my cashflow look like over the next 12 months?") == "cashflow_forecast"
    assert detect_intent("Where am I losing the most money?") == "profitability"
    assert detect_intent("Hello there") == "general_recommendation"


def test_resolve_affected_sectors_milk_price():
    affected, unaffected = resolve_affected_sectors(
        "scenario_milk_price",
        ["dairy", "beef", "lamb"],
    )
    assert affected == ["dairy"]
    assert unaffected == ["beef", "lamb"]


def test_resolve_affected_sectors_feed():
    affected, unaffected = resolve_affected_sectors(
        "scenario_feed_cost",
        ["dairy", "beef"],
    )
    assert affected == ["dairy", "beef"]
    assert unaffected == []


def test_ask_farm_intelligence_response_schema():
    result = ask_farm_intelligence(
        "How healthy is my business?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef", "lamb"],
    )
    assert REQUIRED_RESPONSE_KEYS.issubset(result.keys())
    assert result["intent"] == "health_score"
    assert result["success"] is True
    assert isinstance(result["summary"], str) and result["summary"]
    assert isinstance(result["key_points"], list) and result["key_points"]
    assert isinstance(result["recommendation"], str) and result["recommendation"]
    assert result["metrics"].get("health_score") is not None


def test_milk_price_sector_routing():
    result = ask_farm_intelligence(
        "What happens if milk price increases by 5c/L?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef", "lamb"],
    )
    assert result["intent"] == "scenario_milk_price"
    assert result["affected_sectors"] == ["dairy"]
    assert result["unaffected_sectors"] == ["beef", "lamb"]
    assert "dairy" in result["sector_impact"]
    assert result["sector_impact"]["dairy"]["profit_change"] is not None
    assert result["overall_impact"]["total_profit_change"] is not None


def test_feed_scenario_affects_selected_sectors():
    result = ask_farm_intelligence(
        "What happens if feed costs increase by 10%?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef"],
    )
    assert result["intent"] == "scenario_feed_cost"
    assert set(result["affected_sectors"]) == {"dairy", "beef"}
    assert result["overall_impact"]["total_profit_change"] is not None
    assert result["overall_impact"]["total_profit_change"] < 0


def test_herd_scenario_without_dairy_selected():
    result = ask_farm_intelligence(
        "What if I add 50 cows?",
        farm_file="multi_sector_farm.json",
        sectors=["beef", "lamb"],
    )
    assert result["intent"] == "scenario_herd_size"
    assert result["affected_sectors"] == []
    assert "dairy sector" in result["summary"].lower() or "dairy" in result["summary"].lower()


def test_parse_milk_price_profit_increases():
    result = ask_farm_intelligence(
        "What happens if milk price increases by 5c/L?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef", "lamb"],
    )
    dairy_profit = result["sector_impact"]["dairy"]["profit_change"]
    overall_profit = result["overall_impact"]["total_profit_change"]
    assert dairy_profit > 0
    assert overall_profit == dairy_profit


def test_milk_price_without_dairy_selected():
    result = ask_farm_intelligence(
        "What happens if milk price increases by 5c/L?",
        farm_file="multi_sector_farm.json",
        sectors=["beef", "lamb"],
    )
    assert result["intent"] == "scenario_milk_price"
    assert result["affected_sectors"] == []
    assert set(result["unaffected_sectors"]) == {"beef", "lamb"}


def test_farmer_advisor_api_endpoint():
    response = client.post(
        "/api/farmer/advisor",
        json={
            "question": "What happens if milk price increases by 5c/L?",
            "farm_file": "multi_sector_farm.json",
            "sectors": ["dairy", "beef", "lamb"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "scenario_milk_price"
    assert data["affected_sectors"] == ["dairy"]
    assert data["unaffected_sectors"] == ["beef", "lamb"]
    assert data["summary"]


def test_health_score_uses_plain_english_summary():
    result = ask_farm_intelligence(
        "How healthy is my business?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef", "lamb"],
    )
    assert result["intent"] == "health_score"
    assert "health score" in result["summary"].lower()
    assert "Watch out" in result["summary"] or "Overall risk" in result["summary"] or "stable" in result["summary"].lower()


def test_cashflow_forecast_includes_monthly_insights():
    result = ask_farm_intelligence(
        "What will my cashflow look like over the next 12 months?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef", "lamb"],
    )
    assert result["intent"] == "cashflow_forecast"
    joined = " ".join(result["key_points"]).lower()
    assert "opening cash" in joined
    assert "next phase" not in joined
    assert any(
        token in joined
        for token in ("lowest balance", "year-end running balance", "months below zero", "average monthly cashflow")
    )


def test_profitability_losing_money_mentions_weakest_sector():
    result = ask_farm_intelligence(
        "Where am I losing the most money?",
        farm_file="multi_sector_farm.json",
        sectors=["dairy", "beef", "lamb"],
    )
    assert result["intent"] == "profitability"
    assert "weakest" in result["summary"].lower() or "losing" in result["summary"].lower()
