"""
Dairy statement application service.

Orchestrates the complete internal dairy-statement use case:

    provider selection (get_dairy_statement_provider)
        -> statement retrieval (provider.get_milk_statement)
        -> normalised DairyStatementResponse
        -> dairy statement adapter (adapt_dairy_statement_to_monthly_entry)
        -> financial-engine-compatible monthly-entry dict

This is the single, stable entry point intended for future callers — an API
route, a document-management integration, a background ingestion process, or
an internal financial-analysis workflow — none of which exist yet. This
module adds none of them; it only gives any future caller one place to call
into instead of each reimplementing provider selection and adapter wiring
itself.

No HTTP endpoint, real network call, or database write happens here or
anywhere downstream of here. The active provider for "STRATHROY" remains
``MockDairyStatementProvider`` (via the unchanged Phase 6 factory);
``HttpDairyStatementProvider`` is never imported or instantiated by this
module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from models.dairy_statement import DairyStatementResponse
from services.dairy_statement_adapter import adapt_dairy_statement_to_monthly_entry
from services.dairy_statement_provider import DairyStatementProvider
from services.dairy_statement_provider_factory import get_dairy_statement_provider

# Alias only, to keep the injection point on process_dairy_statement readable.
# Matches get_dairy_statement_provider's own signature -- no new abstraction,
# no DI framework, no service container.
ProviderFactory = Callable[[str], DairyStatementProvider]


@dataclass(frozen=True)
class ProcessedDairyStatement:
    """
    Result of processing one dairy statement end-to-end.

    ``statement`` is the exact, validated ``DairyStatementResponse`` returned
    by the provider — untouched by this service or by the adapter, and
    available here for provider/statement traceability (``statement.provider``,
    ``statement.statement``, etc.) without re-deriving anything.

    ``monthly_entry`` is the adapter's own dict output, exactly as returned by
    ``services.dairy_statement_adapter.adapt_dairy_statement_to_monthly_entry``.
    No second monthly-entry schema is defined here, and no field on it is
    recalculated or overwritten by this service.
    """

    statement: DairyStatementResponse
    monthly_entry: Dict[str, Any]


def process_dairy_statement(
    provider_id: str,
    supplier_no: str,
    invoice_id: str,
    month_no: int,
    year: int,
    *,
    provider_factory: ProviderFactory = get_dairy_statement_provider,
) -> ProcessedDairyStatement:
    """
    Retrieve and adapt one dairy statement, end to end.

    A normal caller only needs the five statement-identifying parameters —
    ``provider_factory`` defaults to the real ``get_dairy_statement_provider``
    and never needs to be supplied outside of tests. Injecting a fake
    provider factory in a test proves this function depends on the
    ``DairyStatementProvider`` abstraction, rather than importing and
    constructing ``MockDairyStatementProvider`` directly.

    This function does not catch or translate any exception, and performs no
    persistence or network call of its own:

    - ``provider_factory(provider_id)`` can raise
      ``UnsupportedDairyProviderError`` (``services/dairy_statement_provider.py``).
    - ``provider.get_milk_statement(...)`` can raise the same
      ``UnsupportedDairyProviderError`` again (a mismatched ``provider_id``
      passed to an already-selected provider), or a pydantic
      ``ValidationError`` (via ``DairyStatementRequest``, for invalid
      ``month_no``/``year``/blank identifiers).
    - ``adapt_dairy_statement_to_monthly_entry(...)`` can raise
      ``UnsupportedStatementCurrencyError`` or ``IncompleteDairyStatementError``
      (``services/dairy_statement_adapter.py``).

    All of the above propagate unchanged, so a caller can catch the specific
    error it cares about instead of a generic ``Exception``.

    Returns:
        ProcessedDairyStatement: the untouched source statement plus the
        adapter's monthly-entry dict.
    """
    provider = provider_factory(provider_id)
    statement = provider.get_milk_statement(
        provider_id=provider_id,
        supplier_no=supplier_no,
        invoice_id=invoice_id,
        month_no=month_no,
        year=year,
    )
    monthly_entry = adapt_dairy_statement_to_monthly_entry(statement)
    return ProcessedDairyStatement(statement=statement, monthly_entry=monthly_entry)
