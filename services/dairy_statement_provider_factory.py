"""
Dairy statement provider factory.

The single place that knows which concrete ``DairyStatementProvider``
implementation corresponds to a given ``provider_id``. Callers should depend
on this factory and on the ``DairyStatementProvider`` protocol — never
directly on a concrete provider class such as ``MockDairyStatementProvider``
— so that re-pointing a provider ID from the mock to a real implementation
in future is a one-line change here, with no change required anywhere else.

    provider = get_dairy_statement_provider("STRATHROY")
    statement = provider.get_milk_statement(
        provider_id="STRATHROY", supplier_no="152", invoice_id="66518",
        month_no=2, year=2026,
    )

No new provider is registered here beyond the existing mock — this module
only makes explicit, indirect access to the existing provider possible; it
does not add a second dairy provider or connect to anything real.
"""

from __future__ import annotations

from typing import Callable, Dict

from services.dairy_statement_provider import (
    DairyStatementProvider,
    UnsupportedDairyProviderError,
)
from services.mock_dairy_statement_provider import (
    SUPPORTED_PROVIDER_NAMES,
    MockDairyStatementProvider,
)

# Maps an exact, canonical provider_id to a zero-argument factory function
# returning a DairyStatementProvider. Built from SUPPORTED_PROVIDER_NAMES —
# the mock provider's own list of provider IDs it knows how to answer for —
# rather than redeclaring "STRATHROY" a second time, so there is exactly one
# place that lists supported provider IDs.
_PROVIDER_FACTORIES: Dict[str, Callable[[], DairyStatementProvider]] = {
    provider_id: MockDairyStatementProvider for provider_id in SUPPORTED_PROVIDER_NAMES
}


def get_dairy_statement_provider(provider_id: str) -> DairyStatementProvider:
    """
    Return the ``DairyStatementProvider`` implementation registered for ``provider_id``.

    Matching is exact and case-sensitive after stripping only surrounding
    whitespace — ``"STRATHROY"`` resolves to the mock implementation,
    ``"strathroy"`` does not. This intentionally matches the strict,
    case-sensitive ``provider_id`` validation already performed inside
    ``MockDairyStatementProvider.get_milk_statement``, so a ``provider_id``
    is either valid at both the selection stage (here) and the
    statement-request stage, or rejected at both — never one without the
    other.

    Raises:
        UnsupportedDairyProviderError: if no provider is registered for the
            exact ``provider_id`` given (after stripping whitespace).
            Reuses the same exception type ``MockDairyStatementProvider``
            raises for an unsupported provider_id, so callers only need to
            catch one exception type regardless of whether the rejection
            happened at selection time (here) or at statement-request time
            (inside the provider).
    """
    factory = _PROVIDER_FACTORIES.get(provider_id.strip())
    if factory is None:
        raise UnsupportedDairyProviderError(
            f"Unsupported dairy provider_id: {provider_id!r}. "
            f"Supported providers: {sorted(_PROVIDER_FACTORIES)}"
        )
    return factory()
