"""Smoke tests for DAIRY Farmer Edition API and legacy routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config.paths import ensure_output_dirs


@pytest.fixture
def client():
    ensure_output_dirs()
    return TestClient(app)


def test_app_imports():
    assert app.title == "FarmBiddy Farmer Edition"


def test_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "Farmer" in data["application"]


def test_legacy_analyse_endpoint(client):
    response = client.post(
        "/api/analyse",
        json={"farm_files": ["dairy_farm_1.json"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] in ("single", "comparison")
    assert len(data["results"]) >= 1


def test_farmer_dashboard(client):
    response = client.get("/api/farmer/dashboard?farm_file=dairy_farm_1.json")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["profile"]["farm_name"]
    assert "kpis" in data


def test_farmer_run_analysis(client):
    response = client.post(
        "/api/farmer/run-analysis",
        json={"farm_file": "dairy_farm_1.json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["forecast_summary"] is not None


def test_farmer_scenario_sandbox(client):
    response = client.post(
        "/api/farmer/scenario-sandbox",
        json={
            "farm_file": "dairy_farm_1.json",
            "milk_price_pct_change": 5,
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_farmer_financial_intelligence(client):
    response = client.get("/api/farmer/financial-intelligence?farm_file=dairy_farm_1.json")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "health_score" in data
    assert "plain_summary" in data


def test_farmer_report_preview(client):
    response = client.get(
        "/api/farmer/report?farm_file=dairy_farm_1.json&report_type=full"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["sections"]) >= 1


def test_frontend_served(client):
    response = client.get("/")
    assert response.status_code == 200
    text = response.text
    assert "FarmBiddy" in text
    assert "Daily Updates" in text
    assert 'id="view-upload"' in text
    assert 'id="daily-form"' in text
