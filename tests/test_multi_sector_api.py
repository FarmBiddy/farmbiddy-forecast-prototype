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
    kpi_ids = [k["id"] for k in data["kpis"]]
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
