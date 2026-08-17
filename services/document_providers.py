"""
Document automation extension point (P2): OCR / bank feed / accounting sync.

FarmBiddy does not implement any automated document capture today - a
farmer types every invoice/receipt in by hand (P1.2). This module defines
the *interface* a future provider would implement, and the *one* ingestion
path that turns whatever it returns into ordinary `Document`s, so that when
one is eventually built it:

  * reuses `services.document_service.add_document` exactly as farmer entry
    does, which means it automatically gets the paid/unpaid financial-effect
    lifecycle, the manual-record duplicate check, and Budget vs
    Actual/Forecast/Alerts visibility for free;
  * cannot silently double-import the same source item, because
    `provider_reference` is enforced unique per farm by `add_document`
    itself - re-running a fetch over an overlapping window is always safe;
  * cannot take down an entire ingestion run over one bad item - each
    provider document is applied independently and a failure is recorded
    against that item, not raised out of `ingest_from_provider`;
  * cannot silently affect a farmer's Actuals: every ingested document is
    created `review_status="pending_review"` (see `models/document.py`),
    so it is visible in the Documents list but has no financial effect
    until the farmer calls `services.document_service.confirm_document`
    (optionally correcting any field first) or discards it with
    `reject_document`.

The shape here deliberately mirrors the existing
`services/dairy_statement_provider.py` + `services/dairy_statement_provider_factory.py`
pair - a `Protocol` contract, an "unsupported" exception, and a small,
explicit factory/registry mapping a source id to an implementation - so
this codebase has one consistent pattern for "an external data source
FarmBiddy doesn't talk to yet, but is designed to". `_PROVIDER_REGISTRY` is
empty by design: no OCR, bank-feed, or accounting-sync integration exists
yet, so `get_document_provider` always raises today. Wiring in a real
provider in future is a one-line addition to that dict, exactly as the
dairy statement factory's own docstring describes for its own registry.

Nothing in this module is wired into the running API or scheduled anywhere;
it exists purely so a real provider (a bank-feed client, an OCR pipeline)
has an obvious, tested seam to plug into, without this prototype pretending
to do OCR or talk to a bank today.
"""

from __future__ import annotations

from typing import Optional, Protocol, TypedDict

from services.document_service import DuplicateProviderReferenceError, add_document


class UnsupportedDocumentProviderError(ValueError):
    """Raised when a requested document source has no registered
    `DocumentProvider` implementation."""


class ProviderDocument(TypedDict, total=False):
    """The shape a provider hands back for one extracted invoice/receipt -
    the same fields a farmer would type in via `DocumentCreate`, plus the
    provider's own stable id for that item and an optional extraction
    confidence/validation signal.

    `category` is always a *suggestion* until the farmer confirms the
    document (see module docstring) - callers should not treat it as
    authoritative for a `pending_review` document.
    """

    provider_reference: str
    document_type: str
    record_type: str
    date: str
    counterparty: str
    amount: float
    category: str
    payment_status: Optional[str]
    payment_date: Optional[str]
    reference: Optional[str]
    attachment_reference: Optional[str]
    notes: Optional[str]
    sector: Optional[str]
    confidence: Optional[float]


class DocumentProvider(Protocol):
    """Interface a future OCR/bank-feed/accounting-sync integration
    implements. `name` must be one of `models.document.DOCUMENT_SOURCES`
    (excluding "manual")."""

    name: str

    def fetch_new(self, farm_file: str, since: str | None) -> list[ProviderDocument]:
        """Return newly available documents for this farm since the given
        ISO date (or all available history if `since` is None). Must not
        raise for "nothing new" - return an empty list instead."""
        ...


# Maps a document source id (see `models.document.DOCUMENT_SOURCES`) to a
# registered `DocumentProvider` instance. Deliberately empty - see module
# docstring. A real integration adds its entry here; nothing else in this
# module, `document_service`, or any caller needs to change.
_PROVIDER_REGISTRY: dict[str, DocumentProvider] = {}


def get_document_provider(source: str) -> DocumentProvider:
    """Return the `DocumentProvider` registered for `source`.

    Raises:
        UnsupportedDocumentProviderError: always today, since no provider is
            registered yet - see `_PROVIDER_REGISTRY`.
    """
    provider = _PROVIDER_REGISTRY.get(source)
    if provider is None:
        raise UnsupportedDocumentProviderError(
            f"Unsupported document source: {source!r}. "
            f"Registered sources: {sorted(_PROVIDER_REGISTRY) or 'none'}"
        )
    return provider


def ingest_from_provider(farm_file: str, provider: DocumentProvider, since: str | None = None) -> dict:
    """Fetch and stage one provider's documents for a farm as
    `review_status="pending_review"` - the farmer must confirm each one
    (`services.document_service.confirm_document`) before it can affect
    Actuals.

    Returns a summary: `{"source", "created": [...], "skipped_duplicate":
    [...], "failed": [{"item", "error"}]}` - never raises for individual
    item problems, so one malformed provider record can't abort a whole
    ingestion run.
    """
    created: list[dict] = []
    skipped_duplicate: list[str] = []
    failed: list[dict] = []

    for item in provider.fetch_new(farm_file, since):
        provider_reference = item.get("provider_reference")
        confidence = item.get("confidence")
        data = {k: v for k, v in item.items() if k not in ("provider_reference", "confidence")}
        try:
            document = add_document(
                farm_file, data,
                source=provider.name,
                provider_reference=provider_reference,
                review_status="pending_review",
                extraction_confidence=confidence,
            )
            created.append(document)
        except DuplicateProviderReferenceError:
            skipped_duplicate.append(provider_reference or "")
        except (ValueError, KeyError) as error:
            failed.append({"item": provider_reference or data.get("reference") or "unknown", "error": str(error)})

    return {
        "source": provider.name,
        "created": created,
        "skipped_duplicate": skipped_duplicate,
        "failed": failed,
    }
