"""Tests for the shared backend currency/percent formatting helpers (Phase 9)."""

from forecast_engine.formatting import format_currency, format_percent


def test_format_currency_positive():
    assert format_currency(1234) == "€1,234"


def test_format_currency_negative_sign_before_symbol():
    """Negative values must read '-€1,234', never '€-1,234'."""
    assert format_currency(-1234) == "-€1,234"


def test_format_currency_zero():
    assert format_currency(0) == "€0"


def test_format_currency_none_defaults_to_zero():
    assert format_currency(None) == "€0"


def test_format_currency_with_decimals():
    assert format_currency(3.456, decimals=2) == "€3.46"
    assert format_currency(-3.456, decimals=2) == "-€3.46"


def test_format_percent_default_one_decimal():
    assert format_percent(12.34) == "12.3%"


def test_format_percent_negative():
    assert format_percent(-5.2) == "-5.2%"


def test_format_percent_custom_decimals():
    assert format_percent(12.345, decimals=0) == "12%"


def test_format_percent_none_defaults_to_zero():
    assert format_percent(None) == "0.0%"
