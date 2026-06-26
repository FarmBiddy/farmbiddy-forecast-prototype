"""Upload ingestion and daily updates (ported from FI engine, adapted for DAIRY)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config.paths import ensure_output_dirs
from services.file_ingestion_service import FileIngestionService


@pytest.fixture
def client():
    ensure_output_dirs()
    return TestClient(app)


def test_upload_parsing_csv(tmp_path):
    csv_content = "Label,Value\nMilk Sales,18500\nFeed Costs,6200\nCash Balance,15000\n"
    csv_path = tmp_path / "test_farm.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    service = FileIngestionService()
    result = service.ingest_file(csv_path, filename="test_farm.csv")
    assert "milk_revenue" in result.detected_fields
    assert "feed_cost" in result.detected_fields
    assert "cash_balance" in result.detected_fields


def test_upload_endpoint(client):
    csv_content = "Label,Value\nMilk Sales,18500\nFeed Costs,6200\nCash Balance,15000\n"
    response = client.post(
        "/api/upload",
        files={"file": ("farm.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["detected_fields"]) >= 3


def test_upload_preview_endpoint(client):
    csv_content = "Label,Value\nMilk Sales,18500\nFeed Costs,6200\n"
    response = client.post(
        "/api/upload/preview",
        files={"file": ("farm.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["upload_id"]
    assert len(data["farmer_categories"]) >= 1


def test_upload_json(tmp_path):
    json_content = json.dumps({
        "milk_revenue": 18500,
        "feed_cost": 6200,
        "cash_balance": 15000,
        "herd_size": 120,
    })
    json_path = tmp_path / "farm.json"
    json_path.write_text(json_content, encoding="utf-8")
    service = FileIngestionService()
    result = service.ingest_file(json_path, filename="farm.json")
    assert len(result.detected_fields) >= 1


def test_daily_update_categories(client):
    response = client.get("/api/daily-updates/categories")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["categories"]) >= 8


def test_daily_updates_save(client):
    response = client.post(
        "/api/daily-updates",
        json={
            "entries": [{"category_id": "feed_costs", "amount": 50.0}],
            "farm_file": "dairy_farm_1.json",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["applied_entries"]) == 1
