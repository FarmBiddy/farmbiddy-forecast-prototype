"""API-level smoke tests for the Simple Farm Setup / onboarding endpoints
(P1.3). Storage isolated to tmp_path so these never touch real
outputs/farm_events/ data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import repositories.category_budgets as budgets_repo
import repositories.onboarding as onboarding_repo
from api.main import app

client = TestClient(app)
FARM = "multi_sector_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch, isolated_db):
    # See tests/test_document_routes.py's isolated_dirs docstring - these
    # routes are also `enforce_farm_access`-gated, so identity/farm
    # resolution must not touch the shared dev SQLite file either.
    monkeypatch.setattr(onboarding_repo, "ONBOARDING_DIR", str(tmp_path / "onboarding"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    yield tmp_path


def test_status_before_completion():
    resp = client.get(f"/api/farmer/onboarding?farm_file={FARM}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["completed"] is False
    assert len(body["farm_types"]) == 7
    assert any(c["id"] == "feed" for c in body["expense_category_choices"])


def test_complete_onboarding_via_api_and_status_reflects_it():
    payload = {
        "farm_type": "dairy",
        "income_items": [{"category": "milk", "annual_amount": 100000}],
        "cost_items": [{"category": "feed", "annual_amount": 25000}],
        "loan_items": [{"lender": "Bank", "monthly_repayment": 400}],
        "current_cash": 8000,
        "year": 2026,
    }
    resp = client.post(f"/api/farmer/onboarding?farm_file={FARM}", json=payload)
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert summary["farm_type"] == "dairy"
    assert summary["income_budgets_set"] == 1
    assert summary["loan_repayments_annual"] == pytest.approx(4800.0)
    assert summary["current_cash"] == pytest.approx(8000.0)

    status_resp = client.get(f"/api/farmer/onboarding?farm_file={FARM}")
    status = status_resp.json()
    assert status["completed"] is True
    assert status["farm_type"] == "dairy"
    assert status["current_cash"] == pytest.approx(8000.0)

    budgets_resp = client.get(f"/api/farmer/category-budgets?farm_file={FARM}&year=2026")
    assert budgets_resp.json()["count"] == 36  # 12 months x (milk + feed + loan_repayments)


def test_invalid_category_returns_422():
    payload = {
        "farm_type": "dairy",
        "income_items": [{"category": "not_real", "annual_amount": 100}],
    }
    resp = client.post(f"/api/farmer/onboarding?farm_file={FARM}", json=payload)
    assert resp.status_code == 422


def test_invalid_farm_type_returns_422():
    payload = {"farm_type": "not_a_farm_type"}
    resp = client.post(f"/api/farmer/onboarding?farm_file={FARM}", json=payload)
    assert resp.status_code == 422
