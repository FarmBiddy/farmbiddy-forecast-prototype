"""Tests for the dairy statement provider factory."""

from __future__ import annotations

import pytest

from models.dairy_statement import DairyStatementResponse
from services.dairy_statement_provider import UnsupportedDairyProviderError
from services.dairy_statement_provider_factory import get_dairy_statement_provider
from services.mock_dairy_statement_provider import MockDairyStatementProvider


def test_strathroy_returns_the_mock_provider():
    provider = get_dairy_statement_provider("STRATHROY")
    assert isinstance(provider, MockDairyStatementProvider)


def test_surrounding_whitespace_is_stripped():
    provider = get_dairy_statement_provider("  STRATHROY  ")
    assert isinstance(provider, MockDairyStatementProvider)


def test_lowercase_provider_id_is_rejected():
    """
    Provider ID matching is strict and case-sensitive, consistent with
    MockDairyStatementProvider.get_milk_statement's own validation — a
    provider_id must be valid (or invalid) at both the selection stage and
    the statement-request stage, never one without the other.
    """
    with pytest.raises(UnsupportedDairyProviderError):
        get_dairy_statement_provider("strathroy")


def test_mixed_case_provider_id_is_rejected():
    with pytest.raises(UnsupportedDairyProviderError):
        get_dairy_statement_provider("StRaThRoY")


def test_unsupported_provider_raises_unsupported_dairy_provider_error():
    with pytest.raises(UnsupportedDairyProviderError):
        get_dairy_statement_provider("UNSUPPORTED_PROVIDER")


def test_returned_object_satisfies_the_provider_abstraction():
    provider = get_dairy_statement_provider("STRATHROY")
    assert hasattr(provider, "get_milk_statement")
    assert callable(provider.get_milk_statement)

    result = provider.get_milk_statement(
        provider_id="STRATHROY",
        supplier_no="152",
        invoice_id="66518",
        month_no=2,
        year=2026,
    )
    assert isinstance(result, DairyStatementResponse)


def test_case_sensitivity_is_consistent_across_selection_and_statement_request():
    """
    A provider_id must be rejected identically whether it fails at the
    selection stage (get_dairy_statement_provider) or would have failed at
    the statement-request stage (get_milk_statement) -- never accepted at
    one layer and rejected at the other.
    """
    with pytest.raises(UnsupportedDairyProviderError):
        get_dairy_statement_provider("strathroy")

    provider = get_dairy_statement_provider("STRATHROY")
    with pytest.raises(UnsupportedDairyProviderError):
        provider.get_milk_statement(
            provider_id="strathroy",
            supplier_no="152",
            invoice_id="66518",
            month_no=2,
            year=2026,
        )
