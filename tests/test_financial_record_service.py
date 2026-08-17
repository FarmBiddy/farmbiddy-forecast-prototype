"""Tests for manual financial-record persistence (P0.2).

Every test points `FINANCIAL_RECORDS_DIR` at a pytest tmp_path so these
never touch the real outputs/farm_events/financial_records/ storage.
"""

from __future__ import annotations

import os

import pytest

import repositories.financial_records as records_repo
import services.financial_record_service as svc


@pytest.fixture(autouse=True)
def isolated_records_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path))
    yield tmp_path


FARM = "test_farm.json"


def _expense(**overrides):
    data = {
        "record_type": "expense",
        "date": "2026-03-10",
        "category": "feed",
        "amount": 250.0,
        "description": "Ration",
        "counterparty": "Co-op",
        "notes": None,
        "sector": None,
    }
    data.update(overrides)
    return data


def _income(**overrides):
    data = {
        "record_type": "income",
        "date": "2026-03-12",
        "category": "milk",
        "amount": 3000.0,
        "description": "Milk cheque",
        "counterparty": "Processor",
        "notes": None,
        "sector": "dairy",
    }
    data.update(overrides)
    return data


def test_add_and_list_financial_record():
    record, dup = svc.add_financial_record(FARM, _expense())
    assert dup is None
    assert record["id"]
    assert record["origin"] == "manual"
    assert record["amount"] == 250.0

    records = svc.list_financial_records(FARM)
    assert len(records) == 1
    assert records[0]["id"] == record["id"]


def test_records_persist_atomically_no_temp_files_left(tmp_path):
    svc.add_financial_record(FARM, _expense())
    svc.add_financial_record(FARM, _income())
    files = os.listdir(tmp_path)
    assert files == [f"{os.path.splitext(FARM)[0]}.json"]


def test_get_financial_record_not_found_raises():
    with pytest.raises(svc.FinancialRecordNotFoundError):
        svc.get_financial_record(FARM, "does-not-exist")


def test_update_financial_record_edits_mutable_fields():
    record, _ = svc.add_financial_record(FARM, _expense())
    updated = svc.update_financial_record(FARM, record["id"], {"amount": 300.0, "notes": "Corrected"})
    assert updated["amount"] == 300.0
    assert updated["notes"] == "Corrected"
    assert updated["updated_at"] >= record["created_at"]
    # Unrelated fields are untouched.
    assert updated["category"] == "feed"


def test_update_financial_record_rejects_unknown_category():
    record, _ = svc.add_financial_record(FARM, _expense())
    with pytest.raises(ValueError):
        svc.update_financial_record(FARM, record["id"], {"category": "not_a_real_category"})


def test_update_financial_record_not_found_raises():
    with pytest.raises(svc.FinancialRecordNotFoundError):
        svc.update_financial_record(FARM, "missing-id", {"amount": 10})


def test_delete_financial_record_removes_it():
    record, _ = svc.add_financial_record(FARM, _expense())
    svc.delete_financial_record(FARM, record["id"])
    assert svc.list_financial_records(FARM) == []


def test_delete_financial_record_twice_raises_not_found():
    record, _ = svc.add_financial_record(FARM, _expense())
    svc.delete_financial_record(FARM, record["id"])
    with pytest.raises(svc.FinancialRecordNotFoundError):
        svc.delete_financial_record(FARM, record["id"])


def test_sector_filtering_includes_whole_farm_records():
    svc.add_financial_record(FARM, _income(sector="dairy"))
    svc.add_financial_record(FARM, _expense(sector="beef"))
    svc.add_financial_record(FARM, _expense(sector=None, description="Whole-farm cost"))

    dairy_only = svc.list_financial_records(FARM, sectors=["dairy"])
    assert len(dairy_only) == 2  # dairy record + the sector-less whole-farm record
    assert all(r.get("sector") in (None, "dairy") for r in dairy_only)


def test_duplicate_hint_flags_but_does_not_block_manual_entry():
    first, dup1 = svc.add_financial_record(FARM, _expense())
    assert dup1 is None
    second, dup2 = svc.add_financial_record(FARM, _expense())
    assert dup2 is not None
    assert dup2["id"] == first["id"]
    # Both records exist - a duplicate hint never blocks manual entry.
    assert len(svc.list_financial_records(FARM)) == 2
    assert second["id"] != first["id"]


def test_origin_document_id_is_enforced_unique():
    svc.add_financial_record(FARM, _expense(), origin="document", origin_document_id="invoice-1")
    with pytest.raises(svc.DuplicateDocumentError):
        svc.add_financial_record(FARM, _expense(description="Same invoice again"), origin="document", origin_document_id="invoice-1")
    assert len(svc.list_financial_records(FARM)) == 1


def test_aggregate_by_category_reconciles_to_manual_totals():
    svc.add_financial_record(FARM, _expense(category="feed", amount=100))
    svc.add_financial_record(FARM, _expense(category="feed", amount=50))
    svc.add_financial_record(FARM, _expense(category="fuel", amount=40))
    svc.add_financial_record(FARM, _income(category="milk", amount=500))

    records = svc.list_financial_records(FARM)
    expense_rows = svc.aggregate_by_category(records, "expense")
    income_rows = svc.aggregate_by_category(records, "income")

    income_total, expense_total = svc.manual_totals(records)
    assert expense_total == round(sum(r["total"] for r in expense_rows), 2)
    assert income_total == round(sum(r["total"] for r in income_rows), 2)

    feed_row = next(r for r in expense_rows if r["category_id"] == "feed")
    assert feed_row["total"] == 150.0
    assert feed_row["count"] == 2


def test_farms_are_isolated_from_each_other():
    svc.add_financial_record("farm_a.json", _expense())
    svc.add_financial_record("farm_b.json", _income())
    assert len(svc.list_financial_records("farm_a.json")) == 1
    assert len(svc.list_financial_records("farm_b.json")) == 1
    assert svc.list_financial_records("farm_a.json")[0]["record_type"] == "expense"
