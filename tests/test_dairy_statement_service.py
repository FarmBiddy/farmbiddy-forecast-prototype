"""
End-to-end tests for the dairy statement application service.

Focused on orchestration behaviour (provider selection -> retrieval ->
adaptation). Value-level checks that are already covered by
tests/test_mock_dairy_statement_provider.py and
tests/test_dairy_statement_integration.py are intentionally not repeated
here beyond what's needed to prove the service wires them together
correctly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from models.dairy_statement import DairyStatementResponse
from services.dairy_statement_provider import UnsupportedDairyProviderError
from services.dairy_statement_service import ProcessedDairyStatement, process_dairy_statement
from services.mock_dairy_statement_provider import MockDairyStatementProvider

_HAPPY_PATH_KWARGS = dict(
    provider_id="STRATHROY",
    supplier_no="152",
    invoice_id="66518",
    month_no=2,
    year=2026,
)


# ---------------------------------------------------------------------------
# 1. Happy-path processing
# ---------------------------------------------------------------------------

def test_happy_path_returns_a_processed_dairy_statement():
    result = process_dairy_statement(**_HAPPY_PATH_KWARGS)
    assert isinstance(result, ProcessedDairyStatement)
    assert isinstance(result.statement, DairyStatementResponse)
    assert isinstance(result.monthly_entry, dict)


def test_happy_path_values_are_correct():
    result = process_dairy_statement(**_HAPPY_PATH_KWARGS)
    statement = result.statement
    entry = result.monthly_entry

    # Source statement — provider/statement traceability, exact sample values.
    assert statement.provider.id == "STRATHROY"
    assert statement.statement.statement_id == "66518"
    assert statement.statement.period.month == 2
    assert statement.statement.period.year == 2026
    assert statement.collections.total_litres == 38804
    assert statement.pricing.gross_price_ppl == Decimal("37.419")
    assert statement.pricing.total_payment == Decimal("14476.66")

    # Adapter output — engine-unit conversion and authoritative revenue.
    assert entry["operational"]["milk_litres"] == 38804.0
    assert entry["pricing"]["milk_price_per_litre"] == 0.37419
    assert entry["revenue"]["milk"] == pytest.approx(14476.66)
    assert entry["revenue"]["total"] == pytest.approx(14476.66)
    assert entry["month"] == 2
    assert entry["year"] == 2026
    assert entry["_source_statement"]["provider_id"] == "STRATHROY"
    assert entry["_source_statement"]["statement_id"] == "66518"


# ---------------------------------------------------------------------------
# 2. Source immutability
# ---------------------------------------------------------------------------

def test_processing_does_not_mutate_the_source_statement():
    """
    The mock provider is deterministic for identical inputs, so a fresh,
    independent call must produce a statement identical to the one returned
    through the service. If the service or the adapter mutated the
    statement in place, this equality would fail.
    """
    baseline = MockDairyStatementProvider().get_milk_statement(**_HAPPY_PATH_KWARGS)
    result = process_dairy_statement(**_HAPPY_PATH_KWARGS)
    assert result.statement.model_dump() == baseline.model_dump()


# ---------------------------------------------------------------------------
# 3. Unsupported provider
# ---------------------------------------------------------------------------

def test_unsupported_provider_raises_unsupported_dairy_provider_error():
    with pytest.raises(UnsupportedDairyProviderError):
        process_dairy_statement(
            provider_id="UNSUPPORTED_PROVIDER",
            supplier_no="152",
            invoice_id="66518",
            month_no=2,
            year=2026,
        )


# ---------------------------------------------------------------------------
# 4. Case sensitivity (matches the Phase 6 decision)
# ---------------------------------------------------------------------------

def test_canonical_provider_id_works():
    result = process_dairy_statement(**_HAPPY_PATH_KWARGS)
    assert result.statement.provider.id == "STRATHROY"


def test_lowercase_provider_id_is_rejected():
    with pytest.raises(UnsupportedDairyProviderError):
        process_dairy_statement(
            provider_id="strathroy",
            supplier_no="152",
            invoice_id="66518",
            month_no=2,
            year=2026,
        )


# ---------------------------------------------------------------------------
# 5. Invalid input
# ---------------------------------------------------------------------------

def test_invalid_month_is_rejected():
    with pytest.raises(ValidationError):
        process_dairy_statement(
            provider_id="STRATHROY",
            supplier_no="152",
            invoice_id="66518",
            month_no=13,
            year=2026,
        )


# ---------------------------------------------------------------------------
# 6. Provider injection / isolation from MockDairyStatementProvider
# ---------------------------------------------------------------------------

class _FakeProvider:
    """Minimal stand-in satisfying the DairyStatementProvider protocol by duck typing."""

    def __init__(self, response: DairyStatementResponse):
        self._response = response
        self.calls = []

    def get_milk_statement(self, provider_id, supplier_no, invoice_id, month_no, year):
        self.calls.append((provider_id, supplier_no, invoice_id, month_no, year))
        return self._response


def test_service_depends_on_the_provider_abstraction_not_the_mock_directly():
    canned_statement = MockDairyStatementProvider().get_milk_statement(**_HAPPY_PATH_KWARGS)
    fake_provider = _FakeProvider(canned_statement)

    result = process_dairy_statement(
        **_HAPPY_PATH_KWARGS,
        provider_factory=lambda provider_id: fake_provider,
    )

    assert fake_provider.calls == [("STRATHROY", "152", "66518", 2, 2026)]
    assert result.statement is canned_statement
    assert result.monthly_entry["revenue"]["milk"] == pytest.approx(14476.66)


# ---------------------------------------------------------------------------
# 7. No double calculation
# ---------------------------------------------------------------------------

def test_revenue_is_not_recomputed_from_litres_times_gross_price():
    result = process_dairy_statement(**_HAPPY_PATH_KWARGS)
    litres = Decimal(str(result.monthly_entry["operational"]["milk_litres"]))
    rate = result.statement.pricing.gross_price_ppl / Decimal("100")
    rate_derived_amount = litres * rate

    # 38,804 x 0.37419 = 14,520.06876 -- deliberately different from the
    # authoritative total_payment of 14,476.66. See
    # docs/dairy_statement_integration.md section 7.
    assert rate_derived_amount != result.statement.pricing.total_payment
    assert Decimal(str(result.monthly_entry["revenue"]["milk"])) == result.statement.pricing.total_payment


# ---------------------------------------------------------------------------
# 8. No network usage
# ---------------------------------------------------------------------------

def test_service_module_has_no_reference_to_the_http_provider():
    """
    services/dairy_statement_service.py must not import or reference
    HttpDairyStatementProvider anywhere -- the normal STRATHROY flow has no
    way to reach it.
    """
    import services.dairy_statement_service as service_module

    assert "HttpDairyStatementProvider" not in dir(service_module)
    assert "http_dairy_statement_provider" not in vars(service_module)


def test_normal_path_succeeds_without_the_http_provider():
    result = process_dairy_statement(**_HAPPY_PATH_KWARGS)
    assert isinstance(result.statement, DairyStatementResponse)
