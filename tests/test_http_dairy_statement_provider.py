"""
Tests for the non-functional HTTP dairy statement provider skeleton.

These tests only confirm the skeleton's own behaviour (instantiation and the
not-configured error). They do not and cannot exercise a real network call,
because services/http_dairy_statement_provider.py imports no HTTP client
library and contains no networking code — see that module's docstring.
"""

from __future__ import annotations

import pytest

from services.http_dairy_statement_provider import (
    DairyStatementProviderNotConfiguredError,
    HttpDairyStatementProvider,
    HttpDairyStatementProviderConfig,
)


def test_can_be_instantiated_with_safe_dummy_configuration():
    config = HttpDairyStatementProviderConfig(
        base_url="https://example.invalid/dairy-provider",
        api_key="dummy-test-key-not-real",
    )
    provider = HttpDairyStatementProvider(config)
    assert provider is not None


def test_default_configuration_has_no_real_url_or_credential():
    config = HttpDairyStatementProviderConfig()
    assert config.base_url == ""
    assert config.api_key is None


def test_constructor_rejects_a_non_config_argument():
    with pytest.raises(TypeError):
        HttpDairyStatementProvider("not-a-config-object")


def test_get_milk_statement_raises_not_configured_error():
    provider = HttpDairyStatementProvider(HttpDairyStatementProviderConfig())
    with pytest.raises(DairyStatementProviderNotConfiguredError):
        provider.get_milk_statement(
            provider_id="STRATHROY",
            supplier_no="152",
            invoice_id="66518",
            month_no=2,
            year=2026,
        )


def test_get_milk_statement_raises_the_same_error_even_with_dummy_configuration():
    """Configuration never enables real behaviour — the skeleton always raises."""
    config = HttpDairyStatementProviderConfig(
        base_url="https://example.invalid/dairy-provider",
        api_key="dummy-test-key-not-real",
    )
    provider = HttpDairyStatementProvider(config)
    with pytest.raises(DairyStatementProviderNotConfiguredError):
        provider.get_milk_statement(
            provider_id="STRATHROY",
            supplier_no="152",
            invoice_id="66518",
            month_no=2,
            year=2026,
        )
