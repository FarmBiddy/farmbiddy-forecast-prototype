"""Tests for the document automation extension point (P2).

Uses a fake in-memory `DocumentProvider` to prove the ingestion path works
end-to-end without any real OCR/bank-feed integration existing.
"""

from __future__ import annotations

import pytest

import services.document_providers as providers
import services.document_service as doc_svc
import services.financial_record_service as record_svc

FARM = "test_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_svc, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(record_svc, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    yield tmp_path


class _FakeBankFeedProvider:
    name = "bank_feed"

    def __init__(self, items):
        self._items = items

    def fetch_new(self, farm_file, since):
        return list(self._items)


def _feed_item(**overrides):
    item = {
        "provider_reference": "txn-001",
        "document_type": "receipt",
        "record_type": "expense",
        "date": "2026-04-01",
        "counterparty": "Co-op",
        "amount": 180.0,
        "category": "feed",
        "payment_status": "paid",
        "payment_date": "2026-04-01",
        "reference": None,
        "attachment_reference": None,
        "notes": None,
        "sector": None,
    }
    item.update(overrides)
    return item


def test_ingest_creates_a_document_with_the_provider_as_source():
    provider = _FakeBankFeedProvider([_feed_item()])
    result = providers.ingest_from_provider(FARM, provider)

    assert result["source"] == "bank_feed"
    assert len(result["created"]) == 1
    assert not result["skipped_duplicate"]
    assert not result["failed"]

    doc = result["created"][0]
    assert doc["source"] == "bank_feed"
    assert doc["provider_reference"] == "txn-001"
    assert doc["linked_financial_record_id"]

    record = record_svc.get_financial_record(FARM, doc["linked_financial_record_id"])
    assert record["origin"] == "document"
    assert record["amount"] == 180.0


def test_re_running_ingest_over_the_same_item_is_a_no_op():
    provider = _FakeBankFeedProvider([_feed_item()])
    providers.ingest_from_provider(FARM, provider)

    second_run = providers.ingest_from_provider(FARM, provider)
    assert second_run["created"] == []
    assert second_run["skipped_duplicate"] == ["txn-001"]
    assert len(doc_svc.list_documents(FARM)) == 1
    assert len(record_svc.list_financial_records(FARM)) == 1


def test_one_bad_item_does_not_abort_the_whole_batch():
    good = _feed_item(provider_reference="txn-good")
    bad = _feed_item(provider_reference="txn-bad", category="not_a_real_category")
    provider = _FakeBankFeedProvider([bad, good])

    result = providers.ingest_from_provider(FARM, provider)

    assert len(result["created"]) == 1
    assert result["created"][0]["provider_reference"] == "txn-good"
    assert len(result["failed"]) == 1
    assert result["failed"][0]["item"] == "txn-bad"


def test_manual_documents_are_unaffected_by_provider_fields():
    manual_doc = doc_svc.add_document(FARM, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-04-02",
        "counterparty": "Mart", "amount": 90.0, "category": "feed",
        "payment_status": None, "payment_date": None, "reference": None,
        "attachment_reference": None, "notes": None, "sector": None,
    })
    assert manual_doc["source"] == "manual"
    assert manual_doc["provider_reference"] is None
