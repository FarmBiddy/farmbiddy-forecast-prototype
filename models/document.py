"""
Invoice/Receipt domain model (P1.2).

A `Document` is metadata about a real-world paper/PDF trail (an invoice a
farmer issued or received, or a receipt for a purchase). It is deliberately
NOT a second, parallel financial ledger - the intended architecture is:

    Invoice/Receipt -> Financial Record -> Actual -> Budget vs Actual
        -> Forecast -> Alert/Insight

so every downstream feature keeps reading from the one `FinancialRecord`
shape (models.financial_record) regardless of whether that record came
from manual entry, a document, or (in future) OCR/a bank feed.

Lifecycle / when a document creates its financial effect
----------------------------------------------------------
FarmBiddy is a cash-flow tool, not an accruals ledger, so a document only
becomes an Actual once the money has actually moved:

  * A RECEIPT is, by definition, proof a payment already happened - it
    defaults to `payment_status="paid"` with `payment_date` = the receipt's
    own `date` unless the farmer says otherwise.
  * An INVOICE defaults to `payment_status="unpaid"` - an invoice on its own
    is a debtor/creditor position, not yet cash in or out, so it does NOT
    create a `FinancialRecord` while unpaid. It shows up in the Documents
    list, but not in Income & Expenses, Budget vs Actual, or the cash
    position, until it is marked paid.

When a document's `payment_status` becomes "paid" (at creation or via
update), `services/document_service.py` creates exactly one linked
`FinancialRecord` dated at `payment_date`, tagged
`origin="document"`/`origin_document_id=<this document's id>` so the
existing per-document uniqueness guard (`financial_record_service`) makes
it impossible for the same document to ever produce two records. If the
document is later marked back to "unpaid" (a correction), the linked
record is removed. Edits to a paid document's amount/category/date resync
the linked record so the two never disagree.

Duplicate prevention against manual entries
--------------------------------------------
If a document's financial effect would exactly match a record the farmer
already entered manually (same date/category/amount/type - the same
heuristic `find_possible_duplicate` already uses for manual entry), no
second `FinancialRecord` is created. The document is still saved (so the
paper trail is on file), but flagged `possible_duplicate_manual_record_id`
so the UI can tell the farmer why no new Actual was added.

No OCR, bank feed, or accounting sync provider is implemented yet, but the
extension point is real, not just a comment: `source` records which kind of
provider produced a document, and `provider_reference` is that provider's
own stable id for the source item (an OCR scan id, a bank transaction id, a
line in an accounting export). `services/document_providers.py` defines the
`DocumentProvider` interface any future integration implements, plus the one
ingestion path (`ingest_from_provider`) that turns its output into
`Document`s through this same model and the same
`services/document_service.add_document` lifecycle every farmer-entered
document already goes through - so a future provider gets duplicate
prevention, the paid/unpaid financial-effect lifecycle, and Budget vs
Actual/Forecast/Alerts visibility for free, with no second code path to
maintain. `attachment_reference` remains a placeholder for wherever the
underlying scanned file/PDF ends up being stored.

Review gate for automated/extracted documents
----------------------------------------------
A farmer typing a document in by hand has, by definition, already reviewed
what they entered - such a document's `review_status` is "confirmed" from
the moment it is created, exactly as before this field existed. A
provider-sourced document (OCR, an emailed invoice, a bank feed line) is
instead created as `review_status="pending_review"`: it is visible in the
Documents list and carries its `extraction_confidence` (if the provider
supplied one) so the farmer can see how sure the extraction was, but it
cannot yet affect financial actuals - `services/document_service.py`'s
`_reconcile_financial_effect` only ever creates/keeps a linked
`FinancialRecord` for a `review_status="confirmed"` document, regardless of
`payment_status`. The farmer moves a pending document to "confirmed" (optionally
correcting any field first) via `confirm_document`, or discards it via
`reject_document` - both in `services/document_service.py`. This keeps the
pipeline explicit end to end:

    raw provider extraction -> ProviderDocument (normalisation)
        -> Document(review_status="pending_review") (staged, no financial effect)
        -> farmer confirms/corrects -> Document(review_status="confirmed")
        -> FinancialRecord (only now) -> Actual -> Budget vs Actual
        -> Forecast -> Alert/Insight
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from models.financial_record import is_valid_category

DOCUMENT_TYPES = ("invoice", "receipt")
PAYMENT_STATUSES = ("unpaid", "paid")
DOCUMENT_SOURCES = ("manual", "ocr", "bank_feed", "accounting_sync")
REVIEW_STATUSES = ("confirmed", "pending_review", "rejected")


class DocumentCreate(BaseModel):
    """Fields a farmer supplies when logging one invoice or receipt."""

    document_type: Literal["invoice", "receipt"]
    record_type: Literal["income", "expense"] = Field(
        ..., description="income = you issued/will receive this; expense = you owe/paid this",
    )
    date: str = Field(..., description="ISO date the document was issued, e.g. 2026-03-15")
    counterparty: str = Field(..., min_length=1, max_length=120, description="Supplier for an expense, customer for income")
    amount: float = Field(..., gt=0)
    category: str
    payment_status: Optional[Literal["unpaid", "paid"]] = Field(
        default=None, description="Defaults to 'paid' for a receipt, 'unpaid' for an invoice",
    )
    payment_date: Optional[str] = Field(default=None, description="ISO date money actually moved; required if paid")
    reference: Optional[str] = Field(default=None, max_length=100, description="Invoice/receipt number")
    attachment_reference: Optional[str] = Field(
        default=None, max_length=500, description="Placeholder for a future scanned/attached file reference",
    )
    notes: Optional[str] = Field(default=None, max_length=1000)
    sector: Optional[str] = Field(default=None, description="dairy/beef/lamb, or omitted for whole-farm/household")

    @field_validator("category")
    @classmethod
    def _category_known(cls, value: str, info) -> str:
        record_type = info.data.get("record_type")
        if record_type and not is_valid_category(record_type, value):
            raise ValueError(f"Unknown {record_type} category '{value}'.")
        return value

    @field_validator("date", "payment_date")
    @classmethod
    def _date_looks_like_iso(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parts = value.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("date must be in YYYY-MM-DD format")
        return value


class DocumentUpdate(BaseModel):
    """Partial update. `document_type` and `record_type` are not editable
    here - changing what a document *is* is a delete-and-recreate."""

    date: Optional[str] = None
    counterparty: Optional[str] = Field(default=None, min_length=1, max_length=120)
    amount: Optional[float] = Field(default=None, gt=0)
    category: Optional[str] = None
    payment_status: Optional[Literal["unpaid", "paid"]] = None
    payment_date: Optional[str] = None
    reference: Optional[str] = Field(default=None, max_length=100)
    attachment_reference: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1000)
    sector: Optional[str] = None

    @field_validator("date", "payment_date")
    @classmethod
    def _date_looks_like_iso(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parts = value.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("date must be in YYYY-MM-DD format")
        return value


class Document(BaseModel):
    """A stored invoice/receipt, with identity, provenance, and the id of
    the FinancialRecord it produced (if any)."""

    id: str
    farm_file: str
    document_type: Literal["invoice", "receipt"]
    record_type: Literal["income", "expense"]
    date: str
    counterparty: str
    amount: float
    category: str
    payment_status: Literal["unpaid", "paid"]
    payment_date: Optional[str] = None
    reference: Optional[str] = None
    attachment_reference: Optional[str] = None
    notes: Optional[str] = None
    sector: Optional[str] = None
    source: Literal["manual", "ocr", "bank_feed", "accounting_sync"] = "manual"
    provider_reference: Optional[str] = Field(
        default=None,
        description="Stable id from the originating provider (OCR/bank feed/accounting sync); unset for farmer-entered documents",
    )
    extraction_confidence: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="Provider-reported confidence in the extracted data (0-1), if supplied; unset for farmer-entered documents",
    )
    review_status: Literal["confirmed", "pending_review", "rejected"] = Field(
        default="confirmed",
        description="'pending_review' blocks any financial effect until the farmer confirms or corrects a provider-sourced document",
    )
    linked_financial_record_id: Optional[str] = None
    possible_duplicate_manual_record_id: Optional[str] = Field(
        default=None,
        description="Set when this document's financial effect matched an existing manual record instead of creating a new one",
    )
    created_at: str
    updated_at: str


class DocumentResponse(BaseModel):
    success: bool = True
    document: Document


class DocumentListResponse(BaseModel):
    success: bool = True
    farm_file: str
    documents: list[Document] = Field(default_factory=list)
    count: int = 0


class DocumentDeleteResponse(BaseModel):
    success: bool = True
    deleted_id: str
