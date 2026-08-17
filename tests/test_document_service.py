"""Tests for invoice/receipt persistence and financial-effect lifecycle (P1.2).

Both DOCUMENTS_DIR and FINANCIAL_RECORDS_DIR are pointed at pytest tmp_path
so these never touch real outputs/farm_events/ storage, and so the
Document -> FinancialRecord linkage can be inspected end-to-end.
"""

from __future__ import annotations

import pytest

import services.document_service as doc_svc
import services.financial_record_service as record_svc

FARM = "test_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_svc, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(record_svc, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    yield tmp_path


def _receipt(**overrides):
    data = {
        "document_type": "receipt",
        "record_type": "expense",
        "date": "2026-03-10",
        "counterparty": "Co-op",
        "amount": 250.0,
        "category": "feed",
        "payment_status": None,
        "payment_date": None,
        "reference": None,
        "attachment_reference": None,
        "notes": None,
        "sector": None,
    }
    data.update(overrides)
    return data


def _invoice(**overrides):
    data = {
        "document_type": "invoice",
        "record_type": "income",
        "date": "2026-03-01",
        "counterparty": "Glanbia",
        "amount": 4200.0,
        "category": "milk",
        "payment_status": None,
        "payment_date": None,
        "reference": "INV-001",
        "attachment_reference": None,
        "notes": None,
        "sector": "dairy",
    }
    data.update(overrides)
    return data


def test_receipt_defaults_to_paid_and_creates_a_linked_financial_record():
    doc = doc_svc.add_document(FARM, _receipt())
    assert doc["payment_status"] == "paid"
    assert doc["payment_date"] == doc["date"]
    assert doc["linked_financial_record_id"]

    record = record_svc.get_financial_record(FARM, doc["linked_financial_record_id"])
    assert record["origin"] == "document"
    assert record["origin_document_id"] == doc["id"]
    assert record["amount"] == 250.0
    assert record["record_type"] == "expense"
    assert record["category"] == "feed"


def test_invoice_defaults_to_unpaid_and_creates_no_financial_record():
    doc = doc_svc.add_document(FARM, _invoice())
    assert doc["payment_status"] == "unpaid"
    assert doc["payment_date"] is None
    assert doc["linked_financial_record_id"] is None
    assert record_svc.list_financial_records(FARM) == []


def test_marking_an_invoice_paid_creates_the_financial_record():
    doc = doc_svc.add_document(FARM, _invoice())
    updated = doc_svc.update_document(FARM, doc["id"], {"payment_status": "paid", "payment_date": "2026-03-20"})
    assert updated["payment_status"] == "paid"
    assert updated["payment_date"] == "2026-03-20"
    assert updated["linked_financial_record_id"]

    record = record_svc.get_financial_record(FARM, updated["linked_financial_record_id"])
    assert record["date"] == "2026-03-20"
    assert record["amount"] == 4200.0
    assert record["record_type"] == "income"


def test_marking_a_paid_document_unpaid_removes_the_financial_record():
    doc = doc_svc.add_document(FARM, _receipt())
    linked_id = doc["linked_financial_record_id"]
    assert linked_id

    updated = doc_svc.update_document(FARM, doc["id"], {"payment_status": "unpaid"})
    assert updated["linked_financial_record_id"] is None
    assert updated["payment_date"] is None
    with pytest.raises(record_svc.FinancialRecordNotFoundError):
        record_svc.get_financial_record(FARM, linked_id)


def test_editing_a_paid_documents_amount_resyncs_the_linked_record():
    doc = doc_svc.add_document(FARM, _receipt(amount=100.0))
    linked_id = doc["linked_financial_record_id"]

    updated = doc_svc.update_document(FARM, doc["id"], {"amount": 175.0})
    assert updated["linked_financial_record_id"] == linked_id
    record = record_svc.get_financial_record(FARM, linked_id)
    assert record["amount"] == 175.0
    # Only one financial record should exist - the original was updated in
    # place, not duplicated.
    assert len(record_svc.list_financial_records(FARM)) == 1


def test_deleting_a_document_cascades_to_its_linked_financial_record():
    doc = doc_svc.add_document(FARM, _receipt())
    linked_id = doc["linked_financial_record_id"]

    doc_svc.delete_document(FARM, doc["id"])
    assert record_svc.list_financial_records(FARM) == []
    with pytest.raises(record_svc.FinancialRecordNotFoundError):
        record_svc.get_financial_record(FARM, linked_id)
    with pytest.raises(doc_svc.DocumentNotFoundError):
        doc_svc.get_document(FARM, doc["id"])


def test_deleting_missing_document_raises():
    with pytest.raises(doc_svc.DocumentNotFoundError):
        doc_svc.delete_document(FARM, "does-not-exist")


def test_updating_missing_document_raises():
    with pytest.raises(doc_svc.DocumentNotFoundError):
        doc_svc.update_document(FARM, "does-not-exist", {"amount": 10.0})


def test_document_matching_an_existing_manual_record_does_not_double_count():
    # Farmer already logged this feed purchase manually...
    record_svc.add_financial_record(FARM, {
        "record_type": "expense", "date": "2026-03-10", "category": "feed",
        "amount": 250.0, "description": "Ration", "counterparty": "Co-op",
        "notes": None, "sector": None,
    })
    # ...then also logs the receipt for the same purchase.
    doc = doc_svc.add_document(FARM, _receipt())

    assert doc["linked_financial_record_id"] is None
    assert doc["possible_duplicate_manual_record_id"]
    # Still exactly one financial record - the manual one, not a second copy.
    assert len(record_svc.list_financial_records(FARM)) == 1


def test_two_documents_with_the_same_date_amount_category_do_not_falsely_flag_each_other():
    doc1 = doc_svc.add_document(FARM, _receipt())
    doc2 = doc_svc.add_document(FARM, _receipt())

    assert doc1["linked_financial_record_id"]
    assert doc2["linked_financial_record_id"]
    assert doc1["linked_financial_record_id"] != doc2["linked_financial_record_id"]
    assert doc1["possible_duplicate_manual_record_id"] is None
    assert doc2["possible_duplicate_manual_record_id"] is None
    assert len(record_svc.list_financial_records(FARM)) == 2


def test_invalid_category_for_record_type_is_rejected():
    with pytest.raises(ValueError):
        doc_svc.add_document(FARM, _receipt(category="milk"))  # milk is an income category


def test_list_documents_filters_by_type_status_and_sector():
    doc_svc.add_document(FARM, _receipt())
    doc_svc.add_document(FARM, _invoice())

    receipts = doc_svc.list_documents(FARM, document_type="receipt")
    assert len(receipts) == 1
    assert receipts[0]["document_type"] == "receipt"

    unpaid = doc_svc.list_documents(FARM, payment_status="unpaid")
    assert len(unpaid) == 1
    assert unpaid[0]["document_type"] == "invoice"

    dairy_only = doc_svc.list_documents(FARM, sectors=["dairy"])
    assert any(d["document_type"] == "invoice" for d in dairy_only)
    # Whole-farm receipt (no sector) is visible under any sector filter.
    assert any(d["document_type"] == "receipt" for d in dairy_only)


def test_documents_are_isolated_per_farm():
    doc_svc.add_document("farm_a.json", _receipt())
    doc_svc.add_document("farm_b.json", _receipt())
    assert len(doc_svc.list_documents("farm_a.json")) == 1
    assert len(doc_svc.list_documents("farm_b.json")) == 1
