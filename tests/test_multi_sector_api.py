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
