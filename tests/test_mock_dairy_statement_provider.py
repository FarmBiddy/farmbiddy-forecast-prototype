"""Tests for the mocked Strathroy dairy statement provider, in isolation from the adapter."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.dairy_statement_provider import UnsupportedDairyProviderError
from services.mock_dairy_statement_provider import MockDairyStatementProvider


@pytest.fixture
def provider() -> MockDairyStatementProvider:
    return MockDairyStatementProvider()


def _get(provider, **overrides):
    params = dict(
        provider_id="STRATHROY",
        supplier_no="152",
        invoice_id="66518",
        month_no=2,
        year=2026,
    )
    params.update(overrides)
    return provider.get_milk_statement(**params)


def test_strathroy_request_succeeds(provider):
    assert _get(provider).success is True


def test_input_supplier_no_is_preserved(provider):
    assert _get(provider, supplier_no="999").supplier.supplier_no == "999"


def test_input_invoice_id_is_preserved(provider):
    assert _get(provider, invoice_id="77001").statement.statement_id == "77001"


def test_input_month_and_year_are_preserved(provider):
    result = _get(provider, month_no=7, year=2027)
    assert result.statement.period.month == 7
    assert result.statement.period.year == 2027


def test_exact_mocked_values_are_returned(provider):
    result = _get(provider)
    assert result.provider.id == "STRATHROY"
    assert result.provider.name == "Strathroy Dairy"
    assert result.supplier.farmer_name == "John Doe Farms Ltd"
    assert result.collections.collection_count == 15
    assert result.collections.total_litres == 38804
    assert result.quality.butterfat_percent == Decimal("4.43")
    assert result.quality.protein_percent == Decimal("3.14")
    assert result.quality.lactose_percent == Decimal("4.62")
    assert result.quality.scc == 249
    assert result.quality.tbc == 10
    assert result.pricing.base_price_ppl == Decimal("33.49")
    assert result.pricing.gross_price_ppl == Decimal("37.419")
    assert result.pricing.vat_percent == Decimal("4.5")
    assert result.pricing.total_payment == Decimal("14476.66")
    assert result.pricing.currency == "EUR"


def test_unsupported_provider_raises_unsupported_dairy_provider_error(provider):
    with pytest.raises(UnsupportedDairyProviderError):
        _get(provider, provider_id="UNSUPPORTED_PROVIDER")


def test_unsupported_provider_error_names_supported_providers(provider):
    with pytest.raises(UnsupportedDairyProviderError, match="STRATHROY"):
        _get(provider, provider_id="UNSUPPORTED_PROVIDER")


def test_provider_id_matching_is_case_sensitive(provider):
    with pytest.raises(UnsupportedDairyProviderError):
        _get(provider, provider_id="strathroy")


def test_invalid_month_rejected_before_provider_lookup(provider):
    with pytest.raises(ValidationError):
        _get(provider, month_no=13)


def test_blank_supplier_no_rejected(provider):
    with pytest.raises(ValidationError):
        _get(provider, supplier_no="")
