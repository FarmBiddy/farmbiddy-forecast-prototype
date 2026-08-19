"""P4.6 demo-farm seed: idempotent, uses live services, does not duplicate dataset actuals."""

from __future__ import annotations

import scripts.seed_demo_farm as seed
from services.category_budget_service import list_category_budgets
from services.document_service import list_documents
from services.financial_record_service import list_financial_records

FARM = "multi_sector_farm.json"


def test_seed_demo_farm_is_idempotent_and_does_not_duplicate_dataset(isolated_db):
    first = seed.seed_demo_farm(FARM)
    assert first["seeded"] is True

    records = list_financial_records(FARM)
    assert any(seed.DEMO_MARKER in (r.get("description") or "") for r in records)
    assert len(records) >= 5
    assert list_category_budgets(FARM)

    docs = list_documents(FARM)
    assert len(docs) >= 6  # 2 base + 4 household

    second = seed.seed_demo_farm(FARM)
    assert second["seeded"] is False
    assert len(list_financial_records(FARM)) == len(records)
    assert len(list_documents(FARM)) == len(docs)


def test_household_documents_have_correct_payment_status(isolated_db):
    seed.seed_demo_farm(FARM)
    docs = list_documents(FARM)
    demo_docs = [d for d in docs if seed.DEMO_MARKER in (d.get("notes") or "")]

    paid_receipts = [d for d in demo_docs if d.get("document_type") == "receipt"]
    unpaid_invoices = [
        d for d in demo_docs
        if d.get("document_type") == "invoice" and d.get("payment_status") == "unpaid"
    ]

    assert len(paid_receipts) >= 3  # 1 base (Diesel) + 2 household
    assert all(d.get("payment_status") == "paid" for d in paid_receipts)
    assert len(unpaid_invoices) >= 3  # 1 base (Silage) + 2 household

    household_categories = {d.get("category") for d in demo_docs if "Household" in (d.get("notes") or "")}
    assert "utilities" in household_categories
    assert "other_expense" in household_categories
