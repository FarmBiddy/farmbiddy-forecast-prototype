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
    against that item, not raised out of `ingest_from_provider`.

Nothing in this module is wired into the running API or scheduled anywhere;
it exists purely so a real provider (a bank-feed client, an OCR pipeline)
has an obvious, tested seam to plug into, without this prototype pretending
to do OCR or talk to a bank today.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from services.document_service import DuplicateProviderReferenceError, add_document


class ProviderDocument(TypedDict, total=False):
    """The shape a provider hands back for one extracted invoice/receipt -
    the same fields a farmer would type in via `DocumentCreate`, plus the
    provider's own stable id for that item."""

    provider_reference: str
    document_type: str
    record_type: str
    date: str
    counterparty: str
    amount: float
    category: str
    payment_status: str | None
    payment_date: str | None
    reference: str | None
    attachment_reference: str | None
    notes: str | None
    sector: str | None


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


def ingest_from_provider(farm_file: str, provider: DocumentProvider, since: str | None = None) -> dict:
    """Fetch and apply one provider's documents for a farm.

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
        data = {k: v for k, v in item.items() if k != "provider_reference"}
        try:
            document = add_document(farm_file, data, source=provider.name, provider_reference=provider_reference)
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
