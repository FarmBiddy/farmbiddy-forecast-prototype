"""
Mocked Strathroy dairy statement provider.

Temporary stand-in for a future document-management-backed or real
provider HTTP client, imitating the shape and values of the
"FarmBiddy Dairy Provider API Example (Strathroy Sample)" reference
document. Implements the ``DairyStatementProvider`` protocol so it can be
swapped for a real provider later without changing any caller.

Makes no network, filesystem, database, or environment-variable calls —
every value returned is either hardcoded from the reference sample or
taken directly from the caller's own input parameters.
"""

from __future__ import annotations

from decimal import Decimal

from models.dairy_statement import (
    DairyCollections,
    DairyPricing,
    DairyProviderInfo,
    DairyQuality,
    DairyStatementInfo,
    DairyStatementPeriod,
    DairyStatementRequest,
    DairyStatementResponse,
    DairySupplierInfo,
)
from services.dairy_statement_provider import UnsupportedDairyProviderError

# Provider IDs this mock knows how to answer for, mapped to their display
# name. Matching is case-sensitive and exact — an unrecognised or
# differently-cased provider_id is treated as unsupported rather than
# silently coerced, since real provider IDs are expected to be fixed,
# known values (e.g. from a future provider registry), not free text.
_SUPPORTED_PROVIDER_NAMES = {
    "STRATHROY": "Strathroy Dairy",
}


class MockDairyStatementProvider:
    """
    Mocked implementation of ``DairyStatementProvider``.

    Supports only ``provider_id == "STRATHROY"``. Returns the exact sample
    values from the reference document for every field the caller does not
    control (quality metrics, pricing, collection volume); the caller's own
    ``supplier_no``, ``invoice_id``, ``month_no``, and ``year`` are always
    reflected back in the response rather than overwritten with sample
    values.
    """

    def get_milk_statement(
        self,
        provider_id: str,
        supplier_no: str,
        invoice_id: str,
        month_no: int,
        year: int,
    ) -> DairyStatementResponse:
        # Validate the shape of the request (non-blank ids, month/year
        # bounds) using the same model the future real provider will use,
        # before even looking at which provider is being asked for.
        request = DairyStatementRequest(
            provider_id=provider_id,
            supplier_no=supplier_no,
            invoice_id=invoice_id,
            month_no=month_no,
            year=year,
        )

        if request.provider_id not in _SUPPORTED_PROVIDER_NAMES:
            raise UnsupportedDairyProviderError(
                f"Unsupported dairy provider_id: {request.provider_id!r}. "
                f"Supported providers: {sorted(_SUPPORTED_PROVIDER_NAMES)}"
            )

        return DairyStatementResponse(
            success=True,
            provider=DairyProviderInfo(
                id=request.provider_id,
                name=_SUPPORTED_PROVIDER_NAMES[request.provider_id],
            ),
            statement=DairyStatementInfo(
                statement_id=request.invoice_id,
                period=DairyStatementPeriod(month=request.month_no, year=request.year),
                payment_date=None,
            ),
            supplier=DairySupplierInfo(
                supplier_no=request.supplier_no,
                farmer_name="John Doe Farms Ltd",
            ),
            collections=DairyCollections(
                collection_count=15,
                total_litres=38804,
            ),
            quality=DairyQuality(
                butterfat_percent=Decimal("4.43"),
                protein_percent=Decimal("3.14"),
                lactose_percent=Decimal("4.62"),
                scc=249,
                tbc=10,
            ),
            pricing=DairyPricing(
                base_price_ppl=Decimal("33.49"),
                gross_price_ppl=Decimal("37.419"),
                vat_percent=Decimal("4.5"),
                total_payment=Decimal("14476.66"),
                currency="EUR",
            ),
        )
