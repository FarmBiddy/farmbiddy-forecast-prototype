"""Tests for the normalised dairy statement domain models (models/dairy_statement.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

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

# Mirrors the "FarmBiddy Dairy Provider API Example (Strathroy Sample)"
# reference document exactly.
_REFERENCE_STATEMENT = {
    "success": True,
    "provider": {"id": "STRATHROY", "name": "Strathroy Dairy"},
    "statement": {
        "statement_id": "66518",
        "period": {"month": 2, "year": 2026},
        "payment_date": None,
    },
    "supplier": {"supplier_no": "152", "farmer_name": "John Doe Farms Ltd"},
    "collections": {"collection_count": 15, "total_litres": 38804},
    "quality": {
        "butterfat_percent": "4.43",
        "protein_percent": "3.14",
        "lactose_percent": "4.62",
        "scc": 249,
        "tbc": 10,
    },
    "pricing": {
        "base_price_ppl": "33.49",
        "gross_price_ppl": "37.419",
        "vat_percent": "4.5",
        "total_payment": "14476.66",
        "currency": "EUR",
    },
}


def test_reference_json_validates_successfully():
    statement = DairyStatementResponse.model_validate(_REFERENCE_STATEMENT)
    assert statement.success is True
    assert statement.provider.id == "STRATHROY"
    assert statement.collections.total_litres == 38804
    assert statement.pricing.total_payment == Decimal("14476.66")


# ---------------------------------------------------------------------------
# Period / month validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("month", [1, 6, 12])
def test_valid_months_accepted(month):
    period = DairyStatementPeriod(month=month, year=2026)
    assert period.month == month


@pytest.mark.parametrize("month", [0, 13, -1])
def test_invalid_months_rejected(month):
    with pytest.raises(ValidationError):
        DairyStatementPeriod(month=month, year=2026)


# ---------------------------------------------------------------------------
# Collections — negative litres rejected
# ---------------------------------------------------------------------------

def test_negative_litres_rejected():
    with pytest.raises(ValidationError):
        DairyCollections(total_litres=-1)


def test_zero_litres_accepted():
    assert DairyCollections(total_litres=0).total_litres == 0


# ---------------------------------------------------------------------------
# Statement info — optional payment date accepts null
# ---------------------------------------------------------------------------

def test_optional_payment_date_accepts_null():
    info = DairyStatementInfo(
        statement_id="66518",
        period=DairyStatementPeriod(month=2, year=2026),
        payment_date=None,
    )
    assert info.payment_date is None


# ---------------------------------------------------------------------------
# Pricing — negative total_payment accepted, currency validated
# ---------------------------------------------------------------------------

def test_negative_total_payment_accepted():
    pricing = DairyPricing(total_payment=Decimal("-250.00"), currency="EUR")
    assert pricing.total_payment == Decimal("-250.00")


@pytest.mark.parametrize("currency", ["EUR", "GBP", "USD"])
def test_valid_currency_codes_accepted(currency):
    assert DairyPricing(total_payment=Decimal("100"), currency=currency).currency == currency


@pytest.mark.parametrize("currency", ["eur", "EURO", "12A", "", "E"])
def test_invalid_currency_codes_rejected(currency):
    with pytest.raises(ValidationError):
        DairyPricing(total_payment=Decimal("100"), currency=currency)


# ---------------------------------------------------------------------------
# Blank required identifiers rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_provider_id_rejected(blank):
    with pytest.raises(ValidationError):
        DairyProviderInfo(id=blank, name="Strathroy Dairy")


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_provider_name_rejected(blank):
    with pytest.raises(ValidationError):
        DairyProviderInfo(id="STRATHROY", name=blank)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_statement_id_rejected(blank):
    with pytest.raises(ValidationError):
        DairyStatementInfo(statement_id=blank, period=DairyStatementPeriod(month=2, year=2026))


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_supplier_no_rejected(blank):
    with pytest.raises(ValidationError):
        DairySupplierInfo(supplier_no=blank)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_request_provider_id_rejected(blank):
    with pytest.raises(ValidationError):
        DairyStatementRequest(
            provider_id=blank, supplier_no="152", invoice_id="66518", month_no=2, year=2026,
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_request_supplier_no_rejected(blank):
    with pytest.raises(ValidationError):
        DairyStatementRequest(
            provider_id="STRATHROY", supplier_no=blank, invoice_id="66518", month_no=2, year=2026,
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_request_invoice_id_rejected(blank):
    with pytest.raises(ValidationError):
        DairyStatementRequest(
            provider_id="STRATHROY", supplier_no="152", invoice_id=blank, month_no=2, year=2026,
        )


# ---------------------------------------------------------------------------
# Quality metrics — optional, never defaulted to zero
# ---------------------------------------------------------------------------

def test_quality_metrics_all_optional_by_default():
    quality = DairyQuality()
    assert quality.butterfat_percent is None
    assert quality.scc is None
    assert quality.tbc is None


def test_quality_metric_negative_rejected():
    with pytest.raises(ValidationError):
        DairyQuality(scc=-1)
