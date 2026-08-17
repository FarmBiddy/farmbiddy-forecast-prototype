"""Tests for the document automation extension point (P2).

Uses a fake in-memory `DocumentProvider` to prove the ingestion path works
end-to-end without any real OCR/bank-feed integration existing: a provider
document is staged as `pending_review` (no financial effect), then the
farmer must explicitly confirm (or reject) it before it can ever touch
Actuals.
"""

from __future__ import annotations

import pytest

import repositories.documents as documents_repo
import repositories.financial_records as records_repo
import services.document_providers as providers
import services.document_service as doc_svc
import services.financial_record_service as record_svc

FARM = "test_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
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
        "confidence": 0.94,
    }
    item.update(overrides)
    return item


# ---------------------------------------------------------------------------
# Ingestion: staged as pending_review, no financial effect yet
# ---------------------------------------------------------------------------

def test_ingest_creates_a_pending_review_document_with_no_financial_effect_yet():
    provider = _FakeBankFeedProvider([_feed_item()])
    result = providers.ingest_from_provider(FARM, provider)

    assert result["source"] == "bank_feed"
    assert len(result["created"]) == 1
    assert not result["skipped_duplicate"]
    assert not result["failed"]

    doc = result["created"][0]
    assert doc["source"] == "bank_feed"
    assert doc["provider_reference"] == "txn-001"
    assert doc["review_status"] == "pending_review"
    assert doc["extraction_confidence"] == 0.94
    # Even though payment_status is "paid", a pending_review document must
    # not yet have any financial effect.
    assert doc["linked_financial_record_id"] is None
    assert record_svc.list_financial_records(FARM) == []


def test_re_running_ingest_over_the_same_item_is_a_no_op():
    provider = _FakeBankFeedProvider([_feed_item()])
    providers.ingest_from_provider(FARM, provider)

    second_run = providers.ingest_from_provider(FARM, provider)
    assert second_run["created"] == []
    assert second_run["skipped_duplicate"] == ["txn-001"]
    assert len(doc_svc.list_documents(FARM)) == 1


def test_one_bad_item_does_not_abort_the_whole_batch():
    good = _feed_item(provider_reference="txn-good")
    bad = _feed_item(provider_reference="txn-bad", category="not_a_real_category")
    provider = _FakeBankFeedProvider([bad, good])

    result = providers.ingest_from_provider(FARM, provider)

    assert len(result["created"]) == 1
    assert result["created"][0]["provider_reference"] == "txn-good"
    assert len(result["failed"]) == 1
    assert result["failed"][0]["item"] == "txn-bad"


def test_manual_documents_are_confirmed_by_default_and_unaffected_by_provider_fields():
    manual_doc = doc_svc.add_document(FARM, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-04-02",
        "counterparty": "Mart", "amount": 90.0, "category": "feed",
        "payment_status": None, "payment_date": None, "reference": None,
        "attachment_reference": None, "notes": None, "sector": None,
    })
    assert manual_doc["source"] == "manual"
    assert manual_doc["provider_reference"] is None
    assert manual_doc["review_status"] == "confirmed"
    # A manual receipt is paid + confirmed from creation, so it DOES get an
    # immediate financial effect - review_status never blocks farmer entry.
    assert manual_doc["linked_financial_record_id"]


# ---------------------------------------------------------------------------
# Farmer review step: confirm / reject
# ---------------------------------------------------------------------------

def test_confirming_a_pending_document_creates_the_financial_record():
    provider = _FakeBankFeedProvider([_feed_item()])
    doc = providers.ingest_from_provider(FARM, provider)["created"][0]
    assert record_svc.list_financial_records(FARM) == []

    confirmed = doc_svc.confirm_document(FARM, doc["id"])
    assert confirmed["review_status"] == "confirmed"
    assert confirmed["linked_financial_record_id"]

    record = record_svc.get_financial_record(FARM, confirmed["linked_financial_record_id"])
    assert record["origin"] == "document"
    assert record["amount"] == 180.0


def test_confirming_with_corrections_applies_them_before_creating_the_record():
    provider = _FakeBankFeedProvider([_feed_item(category="feed")])
    doc = providers.ingest_from_provider(FARM, provider)["created"][0]

    confirmed = doc_svc.confirm_document(FARM, doc["id"], corrections={"category": "veterinary", "amount": 200.0})
    assert confirmed["category"] == "veterinary"
    assert confirmed["amount"] == 200.0
    record = record_svc.get_financial_record(FARM, confirmed["linked_financial_record_id"])
    assert record["category"] == "veterinary"
    assert record["amount"] == 200.0


def test_confirming_with_an_invalid_category_correction_is_rejected():
    provider = _FakeBankFeedProvider([_feed_item()])
    doc = providers.ingest_from_provider(FARM, provider)["created"][0]
    with pytest.raises(ValueError):
        doc_svc.confirm_document(FARM, doc["id"], corrections={"category": "milk"})  # milk is an income category
    # Still pending, still no financial effect.
    assert doc_svc.get_document(FARM, doc["id"])["review_status"] == "pending_review"
    assert record_svc.list_financial_records(FARM) == []


def test_rejecting_a_pending_document_never_creates_a_financial_record():
    provider = _FakeBankFeedProvider([_feed_item()])
    doc = providers.ingest_from_provider(FARM, provider)["created"][0]

    rejected = doc_svc.reject_document(FARM, doc["id"])
    assert rejected["review_status"] == "rejected"
    assert rejected["linked_financial_record_id"] is None
    assert record_svc.list_financial_records(FARM) == []
    # The document itself remains on file for audit purposes.
    assert doc_svc.get_document(FARM, doc["id"])["review_status"] == "rejected"


def test_rejecting_removes_any_financial_effect_already_present():
    # A confirmed, paid document has a financial effect...
    doc = doc_svc.add_document(FARM, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-04-05",
        "counterparty": "Co-op", "amount": 60.0, "category": "feed",
        "payment_status": None, "payment_date": None, "reference": None,
        "attachment_reference": None, "notes": None, "sector": None,
    })
    linked_id = doc["linked_financial_record_id"]
    assert linked_id

    # ...but if it is later rejected (e.g. found to be a mis-scan), the
    # financial effect must be withdrawn, not left dangling.
    rejected = doc_svc.reject_document(FARM, doc["id"])
    assert rejected["linked_financial_record_id"] is None
    with pytest.raises(record_svc.FinancialRecordNotFoundError):
        record_svc.get_financial_record(FARM, linked_id)


def test_confirming_a_pending_document_that_duplicates_a_manual_record_does_not_double_count():
    record_svc.add_financial_record(FARM, {
        "record_type": "expense", "date": "2026-04-01", "category": "feed",
        "amount": 180.0, "description": "Ration", "counterparty": "Co-op",
        "notes": None, "sector": None,
    })
    provider = _FakeBankFeedProvider([_feed_item()])
    doc = providers.ingest_from_provider(FARM, provider)["created"][0]

    confirmed = doc_svc.confirm_document(FARM, doc["id"])
    assert confirmed["linked_financial_record_id"] is None
    assert confirmed["possible_duplicate_manual_record_id"]
    assert len(record_svc.list_financial_records(FARM)) == 1


def test_pending_review_documents_can_be_listed_separately():
    provider = _FakeBankFeedProvider([_feed_item()])
    providers.ingest_from_provider(FARM, provider)
    doc_svc.add_document(FARM, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-04-02",
        "counterparty": "Mart", "amount": 90.0, "category": "feed",
        "payment_status": None, "payment_date": None, "reference": None,
        "attachment_reference": None, "notes": None, "sector": None,
    })

    pending = doc_svc.list_documents(FARM, review_status="pending_review")
    assert len(pending) == 1
    assert pending[0]["source"] == "bank_feed"

    confirmed = doc_svc.list_documents(FARM, review_status="confirmed")
    assert len(confirmed) == 1
    assert confirmed[0]["source"] == "manual"


def test_confirming_or_rejecting_a_missing_document_raises():
    with pytest.raises(doc_svc.DocumentNotFoundError):
        doc_svc.confirm_document(FARM, "does-not-exist")
    with pytest.raises(doc_svc.DocumentNotFoundError):
        doc_svc.reject_document(FARM, "does-not-exist")


# ---------------------------------------------------------------------------
# Provider factory/registry
# ---------------------------------------------------------------------------

def test_get_document_provider_raises_for_any_source_by_default():
    """No real provider is registered yet - the seam exists but resolves to
    nothing, exactly as documented."""
    with pytest.raises(providers.UnsupportedDocumentProviderError):
        providers.get_document_provider("bank_feed")


def test_get_document_provider_resolves_a_registered_provider(monkeypatch):
    fake = _FakeBankFeedProvider([])
    monkeypatch.setitem(providers._PROVIDER_REGISTRY, "bank_feed", fake)
    assert providers.get_document_provider("bank_feed") is fake
