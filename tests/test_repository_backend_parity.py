"""
P3.9 - per-domain backend parity tests.

Each mutable domain (financial records, documents, category budgets,
onboarding) can be cut over from JSON to the database independently by
flipping one environment variable (`config.settings.backend_for`). These
tests run the *same* service-level workflow once per backend for each
domain and assert identical, correct behaviour either way - proof that a
domain can be safely flipped to "db" (or rolled back to "json") without
the service layer or its callers needing to change, which is the whole
point of the repository boundary introduced in P3.1-P3.4.

This is deliberately not "does JSON equal DB bit-for-bit" (irrelevant -
they are different storage engines); it is "does the service layer behave
identically from the outside" - the property that actually matters for a
safe, controlled, per-domain production cutover.
"""

from __future__ import annotations

import pytest

import repositories.category_budgets as budgets_repo
import repositories.documents as documents_repo
import repositories.financial_records as records_repo
import repositories.onboarding as onboarding_repo

BACKENDS = ["json", "db"]


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch, isolated_db):
    # `isolated_db` is requested unconditionally (not just for the "db"
    # backend runs) because DB-backed repositories always resolve a `Farm`
    # row via `identity.seed.get_or_create_farm`, and JSON-backed onboarding
    # export/profile helpers may too - keeping every parametrised run off
    # the real dev database regardless of which domain is under test.
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    monkeypatch.setattr(onboarding_repo, "ONBOARDING_DIR", str(tmp_path / "onboarding"))
    yield tmp_path


@pytest.fixture(params=BACKENDS)
def financial_records_backend(request, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND_FINANCIAL_RECORDS", request.param)
    return request.param


@pytest.fixture(params=BACKENDS)
def documents_backend(request, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND_DOCUMENTS", request.param)
    return request.param


@pytest.fixture(params=BACKENDS)
def category_budgets_backend(request, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND_CATEGORY_BUDGETS", request.param)
    return request.param


@pytest.fixture(params=BACKENDS)
def onboarding_backend(request, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND_ONBOARDING", request.param)
    return request.param


FARM = "parity_test_farm.json"


class TestFinancialRecordsParity:
    def test_add_list_update_delete_and_duplicate_hint(self, financial_records_backend):
        from services.financial_record_service import (
            FinancialRecordNotFoundError,
            add_financial_record,
            delete_financial_record,
            get_financial_record,
            list_financial_records,
            update_financial_record,
        )

        record, duplicate = add_financial_record(FARM, {
            "record_type": "income", "date": "2026-02-01", "category": "milk",
            "amount": 1000.0, "description": "First cheque",
        })
        assert duplicate is None

        _, duplicate = add_financial_record(FARM, {
            "record_type": "income", "date": "2026-02-01", "category": "milk",
            "amount": 1000.0, "description": "Suspiciously identical",
        })
        assert duplicate is not None and duplicate["id"] == record["id"]

        assert len(list_financial_records(FARM)) == 2
        assert len(list_financial_records(FARM, record_type="income")) == 2
        assert len(list_financial_records(FARM, category="does_not_exist")) == 0
        assert get_financial_record(FARM, record["id"])["amount"] == pytest.approx(1000.0)

        updated = update_financial_record(FARM, record["id"], {"amount": 1250.0})
        assert updated["amount"] == pytest.approx(1250.0)

        delete_financial_record(FARM, record["id"])
        with pytest.raises(FinancialRecordNotFoundError):
            get_financial_record(FARM, record["id"])
        assert len(list_financial_records(FARM)) == 1


class TestDocumentsParity:
    def test_pending_review_document_only_gains_a_financial_effect_once_confirmed(self, documents_backend):
        from services.document_service import add_document, confirm_document
        from services.financial_record_service import list_financial_records

        document = add_document(
            FARM,
            {
                "document_type": "invoice", "record_type": "expense", "date": "2026-02-05",
                "counterparty": "Vet Services", "amount": 300.0, "category": "veterinary",
                "payment_status": "paid", "description": "Herd health visit",
            },
            review_status="pending_review",
        )
        # Not yet confirmed - no financial effect, no Actuals impact.
        assert document["linked_financial_record_id"] is None
        assert len(list_financial_records(FARM)) == 0

        confirmed = confirm_document(FARM, document["id"])
        assert confirmed["review_status"] == "confirmed"
        assert confirmed["linked_financial_record_id"]
        assert len(list_financial_records(FARM)) == 1

    def test_paid_document_creates_exactly_one_linked_record(self, documents_backend):
        from services.document_service import add_document
        from services.financial_record_service import list_financial_records

        document = add_document(FARM, {
            "document_type": "receipt", "record_type": "expense", "date": "2026-02-06",
            "counterparty": "Fuel Depot", "amount": 120.0, "category": "fuel",
            "payment_status": "paid", "description": "Diesel",
        })
        assert document["linked_financial_record_id"]
        assert len(list_financial_records(FARM)) == 1

    def test_list_filter_delete_and_missing_document(self, documents_backend):
        from services.document_service import (
            DocumentNotFoundError,
            add_document,
            delete_document,
            get_document,
            list_documents,
        )

        invoice = add_document(FARM, {
            "document_type": "invoice", "record_type": "expense", "date": "2026-02-07",
            "counterparty": "Parts Supplier", "amount": 200.0, "category": "machinery",
            "payment_status": "unpaid", "description": "Parts invoice",
        })
        add_document(FARM, {
            "document_type": "receipt", "record_type": "expense", "date": "2026-02-08",
            "counterparty": "Fuel Depot", "amount": 90.0, "category": "fuel",
            "payment_status": "paid", "description": "Diesel top-up",
        })

        assert len(list_documents(FARM)) == 2
        assert len(list_documents(FARM, document_type="invoice")) == 1
        assert len(list_documents(FARM, payment_status="paid")) == 1

        delete_document(FARM, invoice["id"])
        assert len(list_documents(FARM)) == 1
        with pytest.raises(DocumentNotFoundError):
            get_document(FARM, invoice["id"])


class TestCategoryBudgetsParity:
    def test_monthly_upsert_annual_allocation_and_missing_budget_state(self, category_budgets_backend):
        from services.category_budget_service import (
            budget_lookup,
            list_category_budgets,
            set_annual_budget,
            set_monthly_budget,
        )

        set_monthly_budget(FARM, {
            "sector": None, "record_type": "expense", "category": "feed",
            "year": 2026, "month": 3, "amount": 400.0,
        })
        # Upsert: setting the same slot again replaces, not duplicates.
        set_monthly_budget(FARM, {
            "sector": None, "record_type": "expense", "category": "feed",
            "year": 2026, "month": 3, "amount": 450.0,
        })
        budgets = list_category_budgets(FARM, year=2026)
        assert len(budgets) == 1
        assert budgets[0]["amount"] == pytest.approx(450.0)

        created = set_annual_budget(FARM, {
            "sector": None, "record_type": "expense", "category": "fertiliser",
            "year": 2026, "annual_amount": 1200.0,
        })
        assert len(created) == 12
        assert sum(b["amount"] for b in created) == pytest.approx(1200.0)

        lookup = budget_lookup(FARM)
        assert ("expense", "feed", 2026, 3) in lookup
        # No budget was ever set for "labour" - callers must see an
        # explicit absence, never a fabricated zero.
        assert ("expense", "labour", 2026, 3) not in lookup

    def test_delete_and_missing_budget(self, category_budgets_backend):
        from services.category_budget_service import (
            CategoryBudgetNotFoundError,
            get_category_budget,
            list_category_budgets,
            set_monthly_budget,
        )

        budget = set_monthly_budget(FARM, {
            "sector": None, "record_type": "expense", "category": "fuel",
            "year": 2026, "month": 4, "amount": 150.0,
        })
        assert len(list_category_budgets(FARM, year=2026, category="fuel")) == 1

        from services.category_budget_service import delete_category_budget
        delete_category_budget(FARM, budget["id"])
        assert list_category_budgets(FARM, year=2026, category="fuel") == []
        with pytest.raises(CategoryBudgetNotFoundError):
            get_category_budget(FARM, budget["id"])
        with pytest.raises(CategoryBudgetNotFoundError):
            delete_category_budget(FARM, "does-not-exist")


class TestOnboardingParity:
    def test_complete_onboarding_then_status_reflects_it(self, onboarding_backend):
        from services.onboarding_service import complete_onboarding, get_onboarding_status

        summary = complete_onboarding(FARM, {
            "farm_type": "dairy",
            "current_cash": 8000.0,
            "income_items": [{"category": "milk", "annual_amount": 60000.0}],
            "cost_items": [{"category": "feed", "annual_amount": 20000.0}],
            "loan_items": [{"lender": "Bank", "monthly_repayment": 500.0}],
        })
        assert summary["income_budgets_set"] == 1
        # 1 explicit "feed" cost item + 1 combined loan-repayments line.
        assert summary["cost_budgets_set"] == 2

        status = get_onboarding_status(FARM)
        assert status["completed"] is True
        assert status["farm_type"] == "dairy"
        assert status["current_cash"] == pytest.approx(8000.0)
        assert status["loan_repayments_annual"] == pytest.approx(6000.0)
