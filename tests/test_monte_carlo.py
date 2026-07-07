"""Tests for lightweight Monte Carlo profit outlook."""

from __future__ import annotations

from forecast_engine.monte_carlo import run_monte_carlo
from services.farmer_dashboard_service import run_advanced_forecast
from services.multi_sector_farm import load_farm_for_analysis


def _sample_farm():
    return load_farm_for_analysis("multi_sector_farm.json", ["dairy"])


def test_run_monte_carlo_returns_plain_summary():
    result = run_monte_carlo(_sample_farm(), iterations=200, seed=42)
    assert result.get("plain_summary")
    summary = result["plain_summary"]
    assert "Expected profit is €" in summary
    assert "range between" in summary
    assert "Probability of making a loss is" in summary
    assert summary.endswith("%.")


def test_run_monte_carlo_plain_summary_uses_numeric_fields():
    result = run_monte_carlo(_sample_farm(), iterations=200, seed=42)
    summary = result["plain_summary"]
    assert f"€{result['expected_profit']:,.0f}" in summary
    assert f"€{result['worst_case']:,.0f}" in summary
    assert f"€{result['best_case']:,.0f}" in summary
    loss_pct = f"{result['probability_of_loss'] * 100:.1f}%"
    assert loss_pct in summary


def test_advanced_forecast_includes_plain_summary():
    result = run_advanced_forecast(sectors=["dairy", "beef", "lamb"])
    monte = result.get("monte_carlo") or {}
    assert monte.get("plain_summary")
    assert "scenarios" not in result or result.get("scenarios") in (None, [])
