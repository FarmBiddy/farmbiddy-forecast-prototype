"""Unit tests for executive dashboard summary helpers."""

from __future__ import annotations

from services.dashboard_summary import (
    build_overview_chart_data,
    calculate_dashboard_kpis,
    calculate_sector_performance,
    generate_dashboard_alerts,
    get_historical_data,
    get_selected_sector_data,
    sector_status_label,
    sum_loan_principal,
)


def test_sector_status_label():
    assert sector_status_label(["dairy", "beef", "lamb"]) == "Combined Overview"
    assert sector_status_label(["dairy"]) == "Dairy Only"
    assert sector_status_label(["dairy", "lamb"]) == "Dairy + Lamb Overview"


def test_sum_loan_principal():
    summary = {"loans": [{"principal": 185000}, {"principal": 35000}]}
    assert sum_loan_principal(summary) == 220000


def test_get_selected_sector_data_beef_only():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["beef"])
    assert filtered["selected_sectors"] == ["beef"]
    assert "dairy" not in filtered.get("sectors", {})


def test_calculate_dashboard_kpis_six_cards():
    summary = {"annual_revenue": 1000000, "annual_profit": 150000, "profit_margin": 15.0}
    farm = {"opening_cash_balance": 28500, "_loans": [{"principal": 220000}]}
    monthly = [{"running_balance": 42000}]
    cards = calculate_dashboard_kpis(summary, farm, monthly, "Low")
    assert len(cards) == 6
    ids = [c["id"] for c in cards]
    assert ids == [
        "revenue", "operating_profit", "cash_available",
        "debt_outstanding", "profit_margin", "risk_rating",
    ]
    assert cards[3]["value"] == "€220,000"


def test_calculate_sector_performance_selected_only():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef"])
    rows = calculate_sector_performance(filtered)
    assert len(rows) == 2
    sectors = {r["sector"] for r in rows}
    assert sectors == {"dairy", "beef"}
    for row in rows:
        assert row["revenue"] > 0
        assert "margin_pct" in row
        assert row["status"] in ("Good", "Fair", "Watch")


def test_build_overview_chart_24_months():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    chart = build_overview_chart_data(filtered, months=24)
    assert len(chart) <= 24
    assert len(chart) >= 12
    assert "revenue" in chart[0]
    assert "costs" in chart[0]


def test_generate_dashboard_alerts_max_five():
    farm = {"opening_cash_balance": 500, "feed": 500000}
    summary = {"annual_revenue": 1000000, "annual_profit": -5000, "annual_costs": 1005000}
    kpis = {"monthly_cashflow": -500}
    alerts = generate_dashboard_alerts(farm, summary, kpis, limit=5)
    assert len(alerts) <= 5
    assert all("message" in a for a in alerts)


def test_get_historical_data():
    data = get_historical_data("multi_sector_farm.json", ["lamb"])
    assert data["success"] is True
    assert data["selected_sectors"] == ["lamb"]
    assert len(data["sectors"]) == 1
    assert len(data["combined_monthly"]) >= 12
