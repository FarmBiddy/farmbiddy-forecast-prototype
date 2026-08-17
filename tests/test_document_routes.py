"""API-level smoke tests for the Invoices & Receipts endpoints (P1.2).

Exercises routing/validation through the real FastAPI app, with storage
isolated to tmp_path so these never touch real outputs/farm_events/ data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import repositories.documents as documents_repo
import repositories.financial_records as records_repo
from api.main import app

client = TestClient(app)
FARM = "multi_sector_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch, isolated_db):
    # `isolated_db` (tests/conftest.py) keeps this test's identity/farm
    # resolution (every route here is gated by `enforce_farm_access`) off
    # the shared dev SQLite file, so it can never lock/interfere with a
    # concurrently-running pytest process touching that same file.
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    yield tmp_path


def test_add_list_update_delete_document_via_api():
    create_payload = {
        "document_type": "receipt",
        "record_type": "expense",
        "date": "2026-03-10",
        "counterparty": "Co-op",
        "amount": 250.0,
        "category": "feed",
    }
    resp = client.post(f"/api/farmer/documents?farm_file={FARM}", json=create_payload)
    assert resp.status_code == 200
    doc = resp.json()["document"]
    assert doc["payment_status"] == "paid"
    assert doc["linked_financial_record_id"]

    resp = client.get(f"/api/farmer/documents?farm_file={FARM}")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    resp = client.put(
        f"/api/farmer/documents/{doc['id']}?farm_file={FARM}",
        json={"amount": 300.0},
    )
    assert resp.status_code == 200
    updated = resp.json()["document"]
    assert updated["amount"] == 300.0

    record_resp = client.get(f"/api/farmer/financial-records?farm_file={FARM}")
    assert record_resp.json()["records"][0]["amount"] == 300.0

    del_resp = client.delete(f"/api/farmer/documents/{doc['id']}?farm_file={FARM}")
    assert del_resp.status_code == 200
    assert client.get(f"/api/farmer/documents?farm_file={FARM}").json()["count"] == 0
    assert client.get(f"/api/farmer/financial-records?farm_file={FARM}").json()["count"] == 0


def test_unpaid_invoice_has_no_financial_record_via_api():
    create_payload = {
        "document_type": "invoice",
        "record_type": "income",
        "date": "2026-03-01",
        "counterparty": "Glanbia",
        "amount": 4200.0,
        "category": "milk",
    }
    resp = client.post(f"/api/farmer/documents?farm_file={FARM}", json=create_payload)
    doc = resp.json()["document"]
    assert doc["payment_status"] == "unpaid"
    assert doc["linked_financial_record_id"] is None

    record_resp = client.get(f"/api/farmer/financial-records?farm_file={FARM}")
    assert record_resp.json()["count"] == 0


def test_invalid_category_is_rejected_by_request_validation():
    create_payload = {
        "document_type": "receipt",
        "record_type": "expense",
        "date": "2026-03-10",
        "counterparty": "Co-op",
        "amount": 250.0,
        "category": "milk",  # income category, not valid for an expense
    }
    resp = client.post(f"/api/farmer/documents?farm_file={FARM}", json=create_payload)
    assert resp.status_code == 422


def test_update_missing_document_returns_404():
    resp = client.put(f"/api/farmer/documents/does-not-exist?farm_file={FARM}", json={"amount": 10.0})
    assert resp.status_code == 404


def test_delete_missing_document_returns_404():
    resp = client.delete(f"/api/farmer/documents/does-not-exist?farm_file={FARM}")
    assert resp.status_code == 404
