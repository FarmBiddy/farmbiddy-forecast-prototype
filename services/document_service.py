"""
Invoice/Receipt persistence and financial-effect lifecycle (P1.2).

Storage mirrors `services/financial_record_service.py`: one JSON file per
farm under `config.paths.DOCUMENTS_DIR` (never inside `datasets/`), written
with a temp-file-then-atomic-replace so a crash mid-write can never corrupt
the file, serialised by a process-local lock.

The interesting part of this module is `_reconcile_financial_effect`,
which is the one place that implements the
Invoice/Receipt -> Financial Record architecture decision from
`models/document.py`'s docstring:

  * paid  -> exactly one linked FinancialRecord exists, kept in sync with
             the document's current date/amount/category/counterparty;
  * unpaid -> no linked FinancialRecord exists (any previous one is
              removed - e.g. a farmer un-marking a document paid again);
  * if the document's would-be financial effect exactly matches a record
    the farmer already entered *manually* (same date/category/amount/
    type), no second FinancialRecord is created - the document is flagged
    `possible_duplicate_manual_record_id` instead, so the same real-world
    transaction is never counted twice.

Every create/update/delete of a document runs back through this one
function, so the linked FinancialRecord can never silently drift out of
sync with the document that produced it.

`add_document` also accepts an optional `source`/`provider_reference` pair
(see `models/document.py` and `services/document_providers.py`) so a future
automated provider reuses this exact same creation path - and therefore the
exact same duplicate prevention and financial-effect lifecycle - rather than
a second, parallel one. `provider_reference` is enforced unique per farm so
re-running a provider fetch over the same window can never create a second
document for the same external item.

`review_status` (see `models/document.py`) is a second, independent gate on
top of `payment_status`: `_reconcile_financial_effect` only creates/keeps a
linked `FinancialRecord` when a document is BOTH `payment_status="paid"` AND
`review_status="confirmed"`. A farmer-entered document is "confirmed" from
creation (unchanged behaviour); a provider-sourced document starts
"pending_review" and only gains a financial effect once `confirm_document`
is called, so an OCR/bank-feed extraction never silently touches a farmer's
Actuals before they have seen and accepted it.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from models.document import is_valid_category
from repositories.documents import get_repository
from services.financial_record_service import (
    FinancialRecordNotFoundError,
    add_financial_record,
    delete_financial_record,
    list_financial_records,
    update_financial_record,
)

_LOCK = threading.Lock()


class DocumentNotFoundError(LookupError):
    pass


class DuplicateProviderReferenceError(ValueError):
    """Raised when a provider-sourced document reuses a `provider_reference`
    already on file for this farm - a source item must only ever produce
    one Document, no matter how many times a fetch/ingest cycle runs."""


def _load_documents(farm_file: str) -> list[dict]:
    return get_repository().load(farm_file)


def _save_documents(farm_file: str, documents: list[dict]) -> None:
    get_repository().save(farm_file, documents)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_documents(
    farm_file: str,
    sectors: list[str] | None = None,
    document_type: str | None = None,
    payment_status: str | None = None,
    review_status: str | None = None,
) -> list[dict]:
    """All documents for a farm, newest first, optionally filtered."""
    documents = _load_documents(farm_file)
    if document_type:
        documents = [d for d in documents if d.get("document_type") == document_type]
    if payment_status:
        documents = [d for d in documents if d.get("payment_status") == payment_status]
    if review_status:
        documents = [d for d in documents if d.get("review_status", "confirmed") == review_status]
    if sectors:
        allowed = set(sectors)
        documents = [d for d in documents if not d.get("sector") or d.get("sector") in allowed]
    return sorted(documents, key=lambda d: (d.get("date", ""), d.get("created_at", "")), reverse=True)


def get_document(farm_file: str, document_id: str) -> dict:
    for document in _load_documents(farm_file):
        if document.get("id") == document_id:
            return document
    raise DocumentNotFoundError(document_id)


def _find_manual_duplicate(farm_file: str, record_type: str, date: str, category: str, amount: float) -> dict | None:
    """A manually-entered (non-document-origin) record matching the exact
    same date/category/amount/type this document's financial effect would
    produce. Deliberately origin-scoped to "manual" only, so two unrelated
    documents that happen to share a date/amount/category never falsely
    flag each other as duplicates."""
    for record in list_financial_records(farm_file):
        if (
            record.get("origin") == "manual"
            and record.get("record_type") == record_type
            and record.get("date") == date
            and record.get("category") == category
            and abs(float(record.get("amount") or 0) - float(amount or 0)) < 0.005
        ):
            return record
    return None


def _financial_effect_description(document: dict) -> str:
    label = "Invoice" if document["document_type"] == "invoice" else "Receipt"
    ref = f" (Ref {document['reference']})" if document.get("reference") else ""
    return f"{label} - {document['counterparty']}{ref}"


def _reconcile_financial_effect(farm_file: str, document: dict) -> dict:
    """Bring the linked FinancialRecord (if any) in line with the
    document's current payment_status/review_status/date/amount/category/
    etc. Mutates and returns `document` with `linked_financial_record_id`
    and `possible_duplicate_manual_record_id` set to their correct values.

    A document only ever gets a financial effect when it is BOTH paid AND
    confirmed (see module docstring) - a `pending_review` document is held
    back from Actuals no matter its payment_status, exactly like an unpaid
    document is held back regardless of review_status.
    """
    should_be_linked = (
        document.get("payment_status") == "paid"
        and document.get("review_status", "confirmed") == "confirmed"
    )
    linked_id = document.get("linked_financial_record_id")

    if not should_be_linked:
        if linked_id:
            try:
                delete_financial_record(farm_file, linked_id)
            except FinancialRecordNotFoundError:
                pass
        document["linked_financial_record_id"] = None
        document["possible_duplicate_manual_record_id"] = None
        return document

    effective_date = document.get("payment_date") or document["date"]
    record_data = {
        "record_type": document["record_type"],
        "date": effective_date,
        "category": document["category"],
        "amount": document["amount"],
        "description": _financial_effect_description(document),
        "counterparty": document.get("counterparty"),
        "notes": document.get("notes"),
        "sector": document.get("sector"),
    }

    if linked_id:
        try:
            update_financial_record(farm_file, linked_id, record_data)
            document["possible_duplicate_manual_record_id"] = None
            return document
        except FinancialRecordNotFoundError:
            document["linked_financial_record_id"] = None

    duplicate = _find_manual_duplicate(
        farm_file, document["record_type"], effective_date, document["category"], document["amount"],
    )
    if duplicate:
        document["linked_financial_record_id"] = None
        document["possible_duplicate_manual_record_id"] = duplicate["id"]
        return document

    record, _possible = add_financial_record(
        farm_file, record_data, origin="document", origin_document_id=document["id"],
    )
    document["linked_financial_record_id"] = record["id"]
    document["possible_duplicate_manual_record_id"] = None
    return document


def add_document(
    farm_file: str,
    data: dict,
    source: str = "manual",
    provider_reference: str | None = None,
    review_status: str = "confirmed",
    extraction_confidence: float | None = None,
) -> dict:
    """Create and persist a new invoice/receipt, applying the default
    payment lifecycle (receipts default to paid; invoices default to
    unpaid) and reconciling its financial effect.

    `source`/`provider_reference`/`review_status`/`extraction_confidence`
    are for provider-originated documents (see
    `services/document_providers.py`); farmer-entered documents leave all
    four at their defaults ("manual"/None/"confirmed"/None). A document
    created with `review_status="pending_review"` is saved and listed
    normally but is held back from having any financial effect until
    `confirm_document` is called - see `_reconcile_financial_effect`.
    """
    if not is_valid_category(data["record_type"], data["category"]):
        raise ValueError(f"Unknown {data['record_type']} category '{data['category']}'.")

    with _LOCK:
        documents = _load_documents(farm_file)

        if provider_reference:
            for existing in documents:
                if existing.get("provider_reference") == provider_reference:
                    raise DuplicateProviderReferenceError(
                        f"A document already exists for provider reference '{provider_reference}'.",
                    )

        payment_status = data.get("payment_status") or ("paid" if data["document_type"] == "receipt" else "unpaid")
        payment_date = data.get("payment_date")
        if payment_status == "paid" and not payment_date:
            payment_date = data["date"]
        if payment_status == "unpaid":
            payment_date = None

        now = _now()
        document = {
            "id": uuid.uuid4().hex,
            "farm_file": farm_file,
            "document_type": data["document_type"],
            "record_type": data["record_type"],
            "date": data["date"],
            "counterparty": data["counterparty"],
            "amount": round(float(data["amount"]), 2),
            "category": data["category"],
            "payment_status": payment_status,
            "payment_date": payment_date,
            "reference": data.get("reference"),
            "attachment_reference": data.get("attachment_reference"),
            "notes": data.get("notes"),
            "sector": data.get("sector"),
            "source": source,
            "provider_reference": provider_reference,
            "extraction_confidence": extraction_confidence,
            "review_status": review_status,
            "linked_financial_record_id": None,
            "possible_duplicate_manual_record_id": None,
            "created_at": now,
            "updated_at": now,
        }
        document = _reconcile_financial_effect(farm_file, document)
        documents.append(document)
        _save_documents(farm_file, documents)
        return document


def update_document(farm_file: str, document_id: str, changes: dict) -> dict:
    """Edit a document's fields, then re-reconcile its financial effect so
    the linked FinancialRecord (if any) never drifts out of sync."""
    with _LOCK:
        documents = _load_documents(farm_file)
        for document in documents:
            if document.get("id") != document_id:
                continue

            if "category" in changes and changes["category"] is not None:
                if not is_valid_category(document["record_type"], changes["category"]):
                    raise ValueError(f"Unknown {document['record_type']} category '{changes['category']}'.")

            for field in ("date", "counterparty", "category", "reference", "attachment_reference", "notes", "sector"):
                if field in changes and changes[field] is not None:
                    document[field] = changes[field]
            if "amount" in changes and changes["amount"] is not None:
                document["amount"] = round(float(changes["amount"]), 2)

            if "payment_status" in changes and changes["payment_status"] is not None:
                document["payment_status"] = changes["payment_status"]
                if changes["payment_status"] == "unpaid" and "payment_date" not in changes:
                    document["payment_date"] = None
            if "payment_date" in changes and changes["payment_date"] is not None:
                document["payment_date"] = changes["payment_date"]
            if document["payment_status"] == "paid" and not document.get("payment_date"):
                document["payment_date"] = document["date"]

            document["updated_at"] = _now()
            document = _reconcile_financial_effect(farm_file, document)
            _save_documents(farm_file, documents)
            return document
        raise DocumentNotFoundError(document_id)


def confirm_document(farm_file: str, document_id: str, corrections: dict | None = None) -> dict:
    """Farmer review step for a provider-sourced document: optionally apply
    corrections (same editable fields as `update_document`), then move it to
    `review_status="confirmed"` and reconcile - this is the one moment a
    `pending_review` document can first gain a financial effect. Confirming
    an already-confirmed document (e.g. a manual one) is a harmless no-op
    beyond applying any corrections given.
    """
    with _LOCK:
        documents = _load_documents(farm_file)
        for document in documents:
            if document.get("id") != document_id:
                continue
            for field, value in (corrections or {}).items():
                if field in (
                    "date", "counterparty", "category", "amount", "reference",
                    "attachment_reference", "notes", "sector", "payment_status", "payment_date",
                ) and value is not None:
                    if field == "category" and not is_valid_category(document["record_type"], value):
                        raise ValueError(f"Unknown {document['record_type']} category '{value}'.")
                    document[field] = round(float(value), 2) if field == "amount" else value
            document["review_status"] = "confirmed"
            if document["payment_status"] == "paid" and not document.get("payment_date"):
                document["payment_date"] = document["date"]
            document["updated_at"] = _now()
            document = _reconcile_financial_effect(farm_file, document)
            _save_documents(farm_file, documents)
            return document
        raise DocumentNotFoundError(document_id)


def reject_document(farm_file: str, document_id: str) -> dict:
    """Farmer discards a provider-sourced document as wrong/not theirs. The
    document stays on file (so a farmer can see what was extracted and why
    it was rejected) but is guaranteed to have no financial effect - any
    financial record `_reconcile_financial_effect` may already have created
    is removed here, and `review_status="rejected"` blocks a new one from
    ever being created for this document again."""
    with _LOCK:
        documents = _load_documents(farm_file)
        for document in documents:
            if document.get("id") != document_id:
                continue
            document["review_status"] = "rejected"
            document["updated_at"] = _now()
            document = _reconcile_financial_effect(farm_file, document)
            _save_documents(farm_file, documents)
            return document
        raise DocumentNotFoundError(document_id)


def delete_document(farm_file: str, document_id: str) -> None:
    """Remove a document and cascade-delete its linked FinancialRecord (if
    any), so a removed invoice/receipt never leaves a phantom Actual."""
    with _LOCK:
        documents = _load_documents(farm_file)
        target = next((d for d in documents if d.get("id") == document_id), None)
        if target is None:
            raise DocumentNotFoundError(document_id)
        if target.get("linked_financial_record_id"):
            try:
                delete_financial_record(farm_file, target["linked_financial_record_id"])
            except FinancialRecordNotFoundError:
                pass
        remaining = [d for d in documents if d.get("id") != document_id]
        _save_documents(farm_file, remaining)
