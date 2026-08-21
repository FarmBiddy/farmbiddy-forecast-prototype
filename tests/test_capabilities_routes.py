"""MVP tests for shell capability discovery + dispatcher endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import repositories.documents as documents_repo
import repositories.category_budgets as budgets_repo
import repositories.financial_records as records_repo
from api.main import app

client = TestClient(app)
FARM = "multi_sector_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch, isolated_db):
    # Keep these capability tests fully isolated from real output directories.
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    yield tmp_path


def test_capabilities_list_includes_mvp_keys():
    resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    payload = resp.json()

    keys = {c["key"] for c in payload.get("capabilities", [])}
    assert "dashboard.preview" in keys
    assert "income_expenses.summary" in keys
    assert "documents.list" in keys
    # Phase B reconciliation additions
    for key in (
        "records.list",
        "records.get",
        "records.duplicate_check",
        "documents.get",
        "budgets.list",
        "budgets.get",
        "vocabulary.category_choices",
    ):
        assert key in keys

    # Phase C analytics additions
    phase_c = {c["key"]: c for c in payload.get("capabilities", [])}
    for key in (
        "cashflow.budget_vs_actual",
        "cashflow.actual_series",
        "cashflow.current_period",
        "loans.summary",
        "budgets.variance",
    ):
        assert key in phase_c
    assert "months" in phase_c["cashflow.actual_series"]["optional_params"]
    assert "months" in phase_c["budgets.variance"]["optional_params"]


def test_openapi_includes_new_capability_paths():
    openapi = app.openapi()
    paths = openapi.get("paths") or {}
    assert "/api/v1/capabilities" in paths
    assert "/api/v1/capabilities/{key}/run" in paths


def test_dispatch_dashboard_preview():
    resp = client.post(
        "/api/v1/capabilities/dashboard.preview/run",
        json={
            "farm_file": FARM,
            "sectors": ["dairy", "beef", "lamb"],
            "params": {},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["capability_key"] == "dashboard.preview"
    assert "meta" in payload
    assert "result" in payload
    assert payload["result"]["success"] is True


def test_dispatch_income_expenses_summary():
    resp = client.post(
        "/api/v1/capabilities/income_expenses.summary/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"months": 12}},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["capability_key"] == "income_expenses.summary"
    result = payload["result"]
    assert result["success"] is True
    assert "income_total" in result
    assert "expense_total" in result


def test_dispatch_documents_list_filters_by_payment_status():
    # Create one paid receipt and one unpaid invoice via existing UI routes.
    receipt_payload = {
        "document_type": "receipt",
        "record_type": "expense",
        "date": "2026-03-10",
        "counterparty": "Co-op",
        "amount": 250.0,
        "category": "feed",
    }
    invoice_payload = {
        "document_type": "invoice",
        "record_type": "expense",
        "date": "2026-03-10",
        "counterparty": "Contractor Ltd",
        "amount": 150.0,
        "category": "feed",
    }

    resp1 = client.post(f"/api/farmer/documents?farm_file={FARM}", json=receipt_payload)
    assert resp1.status_code == 200
    assert resp1.json()["document"]["payment_status"] == "paid"

    resp2 = client.post(f"/api/farmer/documents?farm_file={FARM}", json=invoice_payload)
    assert resp2.status_code == 200
    assert resp2.json()["document"]["payment_status"] == "unpaid"

    resp = client.post(
        "/api/v1/capabilities/documents.list/run",
        json={
            "farm_file": FARM,
            "sectors": ["dairy"],
            "params": {"payment_status": "paid"},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["capability_key"] == "documents.list"

    result = payload["result"]
    docs = result.get("documents") or []
    assert len(docs) == 1
    assert docs[0]["payment_status"] == "paid"


def test_dispatch_records_list_and_get():
    create_payload = {
        "record_type": "expense",
        "date": "2026-03-10",
        "category": "feed",
        "amount": 250.0,
        "description": "Ration",
        "counterparty": "Co-op",
        "notes": None,
        "sector": "dairy",
    }
    created_resp = client.post(f"/api/farmer/financial-records?farm_file={FARM}", json=create_payload)
    assert created_resp.status_code == 200
    created = created_resp.json()["record"]
    record_id = created["id"]

    list_resp = client.post(
        "/api/v1/capabilities/records.list/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"record_type": "expense", "category": "feed"}},
    )
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert list_payload["capability_key"] == "records.list"
    assert list_payload["result"]["success"] is True
    records = list_payload["result"]["records"]
    assert any(r["id"] == record_id for r in records)

    get_resp = client.post(
        "/api/v1/capabilities/records.get/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"record_id": record_id}},
    )
    assert get_resp.status_code == 200
    get_payload = get_resp.json()
    assert get_payload["result"]["record"]["id"] == record_id


def test_dispatch_documents_get():
    create_payload = {
        "document_type": "receipt",
        "record_type": "expense",
        "date": "2026-03-10",
        "counterparty": "Co-op",
        "amount": 250.0,
        "category": "feed",
    }
    created_resp = client.post(f"/api/farmer/documents?farm_file={FARM}", json=create_payload)
    assert created_resp.status_code == 200
    created = created_resp.json()["document"]
    document_id = created["id"]

    resp = client.post(
        "/api/v1/capabilities/documents.get/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"document_id": document_id}},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["result"]["document"]["id"] == document_id


def test_dispatch_budgets_list_and_get():
    create_payload = {
        "record_type": "expense",
        "category": "feed",
        "year": 2026,
        "month": 3,
        "amount": 999.0,
        "sector": None,
        "notes": "Test budget",
    }
    created_resp = client.post(
        f"/api/farmer/category-budgets/monthly?farm_file={FARM}",
        json=create_payload,
    )
    assert created_resp.status_code == 200
    created = created_resp.json()["budgets"][0]
    budget_id = created["id"]

    list_resp = client.post(
        "/api/v1/capabilities/budgets.list/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"record_type": "expense", "category": "feed", "year": 2026}},
    )
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    budgets = list_payload["result"]["budgets"]
    assert any(b["id"] == budget_id for b in budgets)

    get_resp = client.post(
        "/api/v1/capabilities/budgets.get/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"budget_id": budget_id}},
    )
    assert get_resp.status_code == 200
    get_payload = get_resp.json()
    assert get_payload["result"]["budget"]["id"] == budget_id


def test_dispatch_vocabulary_category_choices():
    resp = client.post(
        "/api/v1/capabilities/vocabulary.category_choices/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {}},
    )
    assert resp.status_code == 200
    payload = resp.json()
    result = payload["result"]
    assert result["success"] is True
    assert result["income_categories"]
    assert result["expense_categories"]


def test_dispatch_records_duplicate_check_returns_hint():
    # Create one record
    create_payload = {
        "record_type": "expense",
        "date": "2026-03-10",
        "category": "fuel",
        "amount": 123.45,
        "description": "Fuel top-up",
        "counterparty": "Fuel Depot",
        "notes": None,
        "sector": "dairy",
    }
    created_resp = client.post(f"/api/farmer/financial-records?farm_file={FARM}", json=create_payload)
    assert created_resp.status_code == 200

    # Duplicate check for the same values should find the record
    resp = client.post(
        "/api/v1/capabilities/records.duplicate_check/run",
        json={
            "farm_file": FARM,
            "sectors": ["dairy"],
            "params": {
                "record_type": "expense",
                "date": "2026-03-10",
                "category": "fuel",
                "amount": 123.45,
            },
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    result = payload["result"]
    assert result["possible_duplicate"] is True
    assert result["duplicate_of"]["category"] == "fuel"


def test_dispatch_records_get_unknown_id_returns_404():
    resp = client.post(
        "/api/v1/capabilities/records.get/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"record_id": "does-not-exist"}},
    )
    assert resp.status_code == 404


def test_dispatch_documents_get_unknown_id_returns_404():
    resp = client.post(
        "/api/v1/capabilities/documents.get/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {"document_id": "does-not-exist"}},
    )
    assert resp.status_code == 404


def test_dispatch_records_duplicate_check_missing_required_param_returns_422():
    resp = client.post(
        "/api/v1/capabilities/records.duplicate_check/run",
        json={
            "farm_file": FARM,
            "sectors": ["dairy"],
            "params": {
                "record_type": "expense",
                "date": "2026-03-10",
                "category": "fuel",
                # amount missing
            },
        },
    )
    assert resp.status_code == 422


# ── Phase C: cashflow / loans / budget variance ───────────────────────────

def test_dispatch_cashflow_budget_vs_actual():
    resp = client.post(
        "/api/v1/capabilities/cashflow.budget_vs_actual/run",
        json={"farm_file": FARM, "sectors": ["dairy", "beef", "lamb"], "params": {}},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["success"] is True
    assert result["entries"]


def test_dispatch_cashflow_actual_series():
    resp = client.post(
        "/api/v1/capabilities/cashflow.actual_series/run",
        json={"farm_file": FARM, "sectors": ["dairy", "beef", "lamb"], "params": {"months": 6}},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["success"] is True
    assert result["months"] == 6
    series = result["series"]
    assert series
    assert len(series) <= 6
    row = series[0]
    assert "year" in row and "month" in row
    assert "actual_cash_in" in row and "actual_cash_out" in row and "actual_net" in row


def test_dispatch_cashflow_current_period():
    resp = client.post(
        "/api/v1/capabilities/cashflow.current_period/run",
        json={"farm_file": FARM, "sectors": ["dairy", "beef", "lamb"], "params": {}},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["success"] is True
    current = result["current_period"]
    if current is not None:
        assert "income" in current
        assert "costs" in current
        assert "difference" in current


def test_dispatch_loans_summary():
    resp = client.post(
        "/api/v1/capabilities/loans.summary/run",
        json={"farm_file": FARM, "sectors": ["dairy"], "params": {}},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["success"] is True
    assert "total_outstanding_debt" in result
    assert "loan_count" in result
    assert "loans" in result
    assert result["loan_count"] >= 1


def test_dispatch_budgets_variance():
    resp = client.post(
        "/api/v1/capabilities/budgets.variance/run",
        json={"farm_file": FARM, "sectors": ["dairy", "beef", "lamb"], "params": {"months": 12}},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["success"] is True
    assert "overall_status" in result
    assert "categories" in result

