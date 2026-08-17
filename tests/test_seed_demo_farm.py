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
    assert list_documents(FARM)
    assert list_category_budgets(FARM)

    second = seed.seed_demo_farm(FARM)
    assert second["seeded"] is False
    assert len(list_financial_records(FARM)) == len(records)
