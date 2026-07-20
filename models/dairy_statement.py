"""
Normalised dairy statement contract.

This module defines the provider-agnostic data contract for dairy co-op
milk statements, as specified in the "FarmBiddy Dairy Provider API Example
(Strathroy Sample)" reference document.

Scope of this module (domain models only):
- No provider implementation (mock or real) lives here.
- No adapter into the existing financial engine lives here.
- No HTTP endpoint is defined or implied here.
- No unit conversion happens here. Pence-per-litre pricing fields
  (``base_price_ppl``, ``gross_price_ppl``) are stored exactly as received.
  Conversion to EUR-per-litre, if needed, is the responsibility of a future
  adapter layer, not this module.

These models are intentionally isolated from ``models/api_models.py`` so the
whole dairy statement contract can be reviewed, replaced, or removed as one
unit without touching the rest of the API surface.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")

# Sensible four-digit year bounds for a dairy statement period.
MIN_STATEMENT_YEAR = 2000
MAX_STATEMENT_YEAR = 2100


def _ensure_non_blank(value: str, *, field_name: str) -> str:
    """Reject empty or whitespace-only strings without inventing a default."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------

class DairyProviderInfo(BaseModel):
    """Identifies the dairy co-op / processor that issued the statement."""

    id: str = Field(..., description="Provider identifier, e.g. 'STRATHROY'")
    name: str = Field(..., description="Provider display name, e.g. 'Strathroy Dairy'")

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="provider.id")

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="provider.name")


# ---------------------------------------------------------------------------
# Statement identity and period
# ---------------------------------------------------------------------------

class DairyStatementPeriod(BaseModel):
    """The month/year a statement covers."""

    month: int = Field(..., ge=1, le=12, description="Statement month (1-12)")
    year: int = Field(
        ...,
        ge=MIN_STATEMENT_YEAR,
        le=MAX_STATEMENT_YEAR,
        description="Statement year (four digits)",
    )


class DairyStatementInfo(BaseModel):
    """Statement-level identity, period, and payment date."""

    statement_id: str = Field(..., description="Provider's statement/invoice number")
    period: DairyStatementPeriod
    # The reference sample uses null for payment_date. Represented as an
    # explicit Optional — a missing payment date is never invented.
    payment_date: Optional[date] = Field(
        default=None, description="Date payment was made, if known"
    )

    @field_validator("statement_id")
    @classmethod
    def _statement_id_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="statement.statement_id")


# ---------------------------------------------------------------------------
# Supplier (farmer) identity
# ---------------------------------------------------------------------------

class DairySupplierInfo(BaseModel):
    """The farmer/supplier the statement was issued to."""

    supplier_no: str = Field(..., description="Co-op supplier number")
    farmer_name: Optional[str] = Field(default=None, description="Farmer or farm name")

    @field_validator("supplier_no")
    @classmethod
    def _supplier_no_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="supplier.supplier_no")


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

class DairyCollections(BaseModel):
    """Milk collection volume and count for the statement period."""

    collection_count: Optional[int] = Field(
        default=None, ge=0, description="Number of collections in the period"
    )
    total_litres: int = Field(..., ge=0, description="Total litres collected")


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------

class DairyQuality(BaseModel):
    """
    Milk quality metrics.

    All fields are optional because not every provider supplies every metric.
    Missing values stay ``None`` — they are never defaulted to zero, since
    zero carries real quality/financial meaning (e.g. zero SCC is not the
    same as "unknown SCC").

    These metrics are not consumed by any existing forecast, risk, or health
    calculation. They are captured here for traceability only.
    """

    butterfat_percent: Optional[Decimal] = Field(default=None, ge=0)
    protein_percent: Optional[Decimal] = Field(default=None, ge=0)
    lactose_percent: Optional[Decimal] = Field(default=None, ge=0)
    scc: Optional[int] = Field(default=None, ge=0, description="Somatic cell count")
    tbc: Optional[int] = Field(default=None, ge=0, description="Total bacterial count")


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

class DairyPricing(BaseModel):
    """
    Pricing and payment for the statement period.

    ``base_price_ppl`` and ``gross_price_ppl`` are stored exactly as supplied
    by the provider, in pence per litre — no conversion happens in this
    module. ``gross_price_ppl`` is the approved source for deriving an
    effective monthly milk price; ``base_price_ppl`` is kept as reference
    data only.

    ``total_payment`` deliberately has no lower-bound constraint. Dairy
    statements may include negative corrections, clawbacks, or adjustments,
    so a negative value is valid business data, not an error.
    """

    base_price_ppl: Optional[Decimal] = Field(
        default=None, ge=0, description="Base price, pence per litre (reference data)"
    )
    gross_price_ppl: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Gross price, pence per litre (source for effective milk price)",
    )
    vat_percent: Optional[Decimal] = Field(default=None, ge=0)
    total_payment: Decimal = Field(
        ...,
        description=(
            "Total payment due, in the statement currency. May be negative "
            "to represent a correction, clawback, or adjustment."
        ),
    )
    currency: str = Field(..., description="Uppercase ISO-style currency code, e.g. 'EUR'")

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if not CURRENCY_CODE_PATTERN.fullmatch(value):
            raise ValueError(
                f"currency must be an uppercase 3-letter ISO-style code (e.g. 'EUR'), "
                f"got {value!r}"
            )
        return value


# ---------------------------------------------------------------------------
# Full statement response
# ---------------------------------------------------------------------------

class DairyStatementResponse(BaseModel):
    """
    Normalised dairy statement contract returned by any
    :class:`~services.dairy_statement_provider.DairyStatementProvider`
    implementation (mock today, a real HTTP-backed provider in future).
    """

    success: bool
    provider: DairyProviderInfo
    statement: DairyStatementInfo
    supplier: DairySupplierInfo
    collections: DairyCollections
    quality: DairyQuality
    pricing: DairyPricing

    # Landing zone for provider-specific fields that do not (yet) have a
    # place in the shared schema, e.g. a levy breakdown or bonus schedule
    # unique to one co-op. The adapter and financial engine never read this
    # field — only the explicitly named, typed fields above are mapped —
    # so core financial logic has no dependency on its contents.
    provider_specific_data: Optional[Dict[str, Any]] = Field(default=None)


# ---------------------------------------------------------------------------
# Request contract (mirrors Norma's get_milk_statement signature)
# ---------------------------------------------------------------------------

class DairyStatementRequest(BaseModel):
    """Input parameters for requesting a single dairy statement."""

    provider_id: str = Field(..., description="Provider identifier, e.g. 'STRATHROY'")
    supplier_no: str = Field(..., description="Co-op supplier number")
    invoice_id: str = Field(..., description="Provider's statement/invoice number")
    month_no: int = Field(..., ge=1, le=12, description="Statement month (1-12)")
    year: int = Field(..., ge=MIN_STATEMENT_YEAR, le=MAX_STATEMENT_YEAR)

    @field_validator("provider_id")
    @classmethod
    def _provider_id_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="provider_id")

    @field_validator("supplier_no")
    @classmethod
    def _supplier_no_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="supplier_no")

    @field_validator("invoice_id")
    @classmethod
    def _invoice_id_not_blank(cls, value: str) -> str:
        return _ensure_non_blank(value, field_name="invoice_id")
