"""Tests for the canonical health-score formula (Phase 7 / UX items 4-5).

Verifies the shared `calculate_health_score` behaves correctly in isolation
and that the surfaces which used to compute their own number (dashboard
snapshot, Farm Intelligence, the advisor) now agree with each other.
"""

from __future__ import annotations

from forecast_engine.health_score import calculate_health_score
from services.dashboard_summary import calculate_financial_health_snapshot
from services.farmer_dashboard_service import _health_breakdown
from services.financial_intelligence_service import get_financial_intelligence


def test_calculate_health_score_strong_farm():
    forecast = {
        "profit_margin": 25,
        "risk_level": "Low",
        "feed_cost_ratio": 28,
        "monthly_cashflow": 4000,
        "annual_revenue": 500000,
        "annual_costs": 350000,
    }
    farm = {"opening_cash_balance": 50000, "loan_repayments": 10000}
    health = calculate_health_score(forecast, farm)
    assert health["score"] > 70
    assert health["label"] in ("Good", "Excellent")
    assert health["profitability"] == "Good"
    assert health["cashflow"] == "Good"
    assert health["debt_pressure"] == "Low"


def test_calculate_health_score_weak_farm():
    forecast = {
        "profit_margin": 2,
        "risk_level": "High",
        "feed_cost_ratio": 45,
        "monthly_cashflow": -1000,
        "annual_revenue": 200000,
        "annual_costs": 195000,
    }
    farm = {"opening_cash_balance": 1000, "loan_repayments": 40000}
    health = calculate_health_score(forecast, farm)
    assert health["score"] < 50
    assert health["label"] == "Needs attention"
    assert health["cashflow"] == "Negative"
    assert health["debt_pressure"] == "High"


def test_dashboard_snapshot_overall_health_matches_canonical_label():
    forecast_summary = {"profit_margin": 25, "annual_revenue": 500000, "annual_costs": 350000}
    kpis_block = {"feed_cost_ratio": 28, "monthly_cashflow": 4000}
    farm = {"opening_cash_balance": 50000, "loan_repayments": 10000, "debtors": 5000, "creditors": 2000}

    canonical = calculate_health_score({
        "profit_margin": forecast_summary["profit_margin"],
        "risk_level": "Low",
        "feed_cost_ratio": kpis_block["feed_cost_ratio"],
        "monthly_cashflow": kpis_block["monthly_cashflow"],
        "annual_revenue": forecast_summary["annual_revenue"],
        "annual_costs": forecast_summary["annual_costs"],
    }, farm)

    snapshot = calculate_financial_health_snapshot(forecast_summary, farm, kpis_block, "Low")
    by_key = {row["key"]: row for row in snapshot}

    assert by_key["profitability"]["status"] == canonical["profitability"]
    assert by_key["cash_flow"]["status"] == canonical["cashflow"]
    assert by_key["leverage"]["status"] == canonical["debt_pressure"]
    assert by_key["overall_health"]["status"] in ("Good", "Fair", "Watch")


def test_farmer_dashboard_health_breakdown_matches_canonical():
    forecast = {
        "profit_margin": 12,
        "risk_level": "Medium",
        "feed_cost_ratio": 33,
        "monthly_cashflow": 1500,
        "annual_revenue": 300000,
        "annual_costs": 260000,
    }
    farm = {"opening_cash_balance": 15000, "loan_repayments": 20000}
    canonical = calculate_health_score(forecast, farm)
    breakdown = _health_breakdown(forecast, farm)
    assert breakdown["score"] == canonical["score"]
    assert breakdown["label"] == canonical["label"]
    assert breakdown["profitability"] == canonical["profitability"]


def test_financial_intelligence_health_score_uses_canonical_shape():
    data = get_financial_intelligence("multi_sector_farm.json", sectors=["dairy", "beef", "lamb"])
    health = data["health_score"]
    assert set(("score", "label", "profitability", "cashflow", "feed_pressure", "debt_pressure", "risk_level")) <= set(health.keys())
    assert 0 <= health["score"] <= 100
