"""
Integration tests for the mock dairy provider -> adapter -> existing engine flow.

Covers the full path requested for Phase 4 integration validation:

    Mock dairy provider
        -> Normalised dairy statement model
        -> Dairy statement adapter
        -> Existing monthly-entry consumer (services.multi_sector_farm)
        -> Existing financial engine (forecast_engine)

This file adds assertions only. It does not change forecast, scenario,
dashboard, or API behaviour, and it never reads or writes
datasets/multi_sector_farm.json for anything other than a before/after
read-only comparison (see test_existing_dataset_sectors_unaffected).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue
from models.multi_sector_farm import MULTI_SECTOR_FILE
from services.dairy_statement_adapter import adapt_dairy_statement_to_monthly_entry
from services.dairy_statement_provider import UnsupportedDairyProviderError
from services.mock_dairy_statement_provider import MockDairyStatementProvider
from services.multi_sector_farm import (
    aggregate_sector_financials,
    filter_farm_by_sectors,
    load_multi_sector_farm,
    to_legacy_farm_dict,
)

# Exact Strathroy sample inputs specified for this integration test.
_PROVIDER_ID = "STRATHROY"
_SUPPLIER_NO = "152"
_INVOICE_ID = "66518"
_MONTH_NO = 2
_YEAR = 2026


@pytest.fixture
def strathroy_statement():
    provider = MockDairyStatementProvider()
    return provider.get_milk_statement(
        provider_id=_PROVIDER_ID,
        supplier_no=_SUPPLIER_NO,
        invoice_id=_INVOICE_ID,
        month_no=_MONTH_NO,
        year=_YEAR,
    )


@pytest.fixture
def monthly_entry(strathroy_statement):
    return adapt_dairy_statement_to_monthly_entry(strathroy_statement)


def _fake_dairy_only_farm(entry: dict) -> dict:
    """Minimal, valid multi-sector farm shell containing only the adapted entry."""
    return {
        "farm_name": "Integration Test Farm",
        "schema_version": "2.0",
        "farm_summary": {"opening_cash_balance": 0, "loans": []},
        "scheme_payments": {
            "biss": 0,
            "acres": 0,
            "other_grants": 0,
            "scheme_payment_months": {},
        },
        "available_sectors": ["dairy"],
        "sectors": {"dairy": {"monthly": [entry]}},
    }


# ---------------------------------------------------------------------------
# 1-3: mock provider -> model -> adapter
# ---------------------------------------------------------------------------

def test_mock_provider_returns_strathroy(strathroy_statement):
    assert strathroy_statement.success is True
    assert strathroy_statement.provider.id == "STRATHROY"


def test_adapter_accepts_the_statement_and_returns_a_dict(monthly_entry):
    assert isinstance(monthly_entry, dict)


# ---------------------------------------------------------------------------
# 4: shape matches what services/multi_sector_farm.py expects
# ---------------------------------------------------------------------------

def test_monthly_entry_has_expected_top_level_shape(monthly_entry):
    assert set(monthly_entry.keys()) >= {
        "year", "month", "period", "operational", "pricing", "revenue", "costs",
    }
    assert isinstance(monthly_entry["operational"], dict)
    assert isinstance(monthly_entry["pricing"], dict)
    assert isinstance(monthly_entry["revenue"], dict)
    assert isinstance(monthly_entry["costs"], dict)


def test_monthly_entry_flows_through_aggregate_sector_financials(monthly_entry):
    """The real, unmodified aggregation function must accept this entry without error."""
    farm = _fake_dairy_only_farm(monthly_entry)
    filtered = filter_farm_by_sectors(farm, ["dairy"])
    aggregated = aggregate_sector_financials(filtered)

    assert aggregated["dairy"]["annual_milk_litres"] == 38804
    assert aggregated["revenue_totals"]["milk"] == pytest.approx(14476.66)


def test_monthly_entry_flows_through_to_legacy_farm_dict_and_forecast_engine(monthly_entry):
    """Confirm the full path reaches the existing, unmodified forecast_engine."""
    farm = _fake_dairy_only_farm(monthly_entry)
    filtered = filter_farm_by_sectors(farm, ["dairy"])
    aggregated = aggregate_sector_financials(filtered)
    legacy = to_legacy_farm_dict(aggregated, farm)

    revenue = calculate_revenue(legacy)
    costs = calculate_costs(legacy)
    profit = calculate_profit(revenue, costs)
    assert profit == revenue - costs


def test_forecast_engine_milk_revenue_needs_herd_counts_not_supplied_here(monthly_entry):
    """
    Known limitation, confirmed rather than assumed: forecast_engine.calculate_revenue
    computes milk revenue as milking_cows * litres_per_cow * milk_price -- it does not
    read aggregated revenue totals directly. A milk statement carries no herd counts
    (see services/dairy_statement_adapter.py module docstring), so milking_cows and
    litres_per_cow both come out as 0 for a farm built from this entry alone, and
    calculate_revenue's milk component is therefore 0 even though the real payment
    (14,476.66) is correctly captured elsewhere (aggregated revenue_totals, and
    monthly_entry["revenue"]["milk"]). This is a genuine, documented data-availability
    gap, not something this test or the adapter should paper over.
    """
    farm = _fake_dairy_only_farm(monthly_entry)
    filtered = filter_farm_by_sectors(farm, ["dairy"])
    aggregated = aggregate_sector_financials(filtered)
    legacy = to_legacy_farm_dict(aggregated, farm)

    assert legacy["milking_cows"] == 0
    assert legacy["litres_per_cow"] == 0
    assert calculate_revenue(legacy) == 0

    # The real revenue figure is not lost -- it is simply captured one level
    # up, before the herd-count-driven forecast formula discards it.
    assert aggregated["revenue_totals"]["milk"] == pytest.approx(14476.66)
    assert monthly_entry["revenue"]["milk"] == pytest.approx(14476.66)


# ---------------------------------------------------------------------------
# 5: exact values preserved through the pipeline
# ---------------------------------------------------------------------------

def test_total_litres_preserved(monthly_entry):
    assert monthly_entry["operational"]["milk_litres"] == 38804.0


def test_gross_milk_price_is_the_engine_unit(monthly_entry):
    # gross_price_ppl (37.419 pence/litre) / 100 = 0.37419 EUR/litre exactly.
    assert monthly_entry["pricing"]["milk_price_per_litre"] == 0.37419


def test_base_price_remains_available_as_reference_data(strathroy_statement):
    # base_price_ppl is never used to derive the engine price, but it must
    # still be present and readable on the source model as reference data.
    assert strathroy_statement.pricing.base_price_ppl == Decimal("33.49")


def test_realised_total_payment(strathroy_statement, monthly_entry):
    assert strathroy_statement.pricing.total_payment == Decimal("14476.66")
    assert monthly_entry["revenue"]["milk"] == pytest.approx(14476.66)
    assert monthly_entry["revenue"]["total"] == pytest.approx(14476.66)


def test_provider_id_preserved(strathroy_statement, monthly_entry):
    assert strathroy_statement.provider.id == "STRATHROY"
    assert monthly_entry["_source_statement"]["provider_id"] == "STRATHROY"


def test_statement_id_preserved(strathroy_statement, monthly_entry):
    assert strathroy_statement.statement.statement_id == "66518"
    assert monthly_entry["_source_statement"]["statement_id"] == "66518"


def test_month_and_year_preserved(strathroy_statement, monthly_entry):
    assert strathroy_statement.statement.period.month == 2
    assert strathroy_statement.statement.period.year == 2026
    assert monthly_entry["month"] == 2
    assert monthly_entry["year"] == 2026


def test_quality_metrics_preserved(strathroy_statement, monthly_entry):
    assert strathroy_statement.quality.butterfat_percent == Decimal("4.43")
    assert strathroy_statement.quality.protein_percent == Decimal("3.14")
    assert strathroy_statement.quality.lactose_percent == Decimal("4.62")
    assert strathroy_statement.quality.scc == 249
    assert strathroy_statement.quality.tbc == 10

    quality = monthly_entry["quality"]
    assert quality["butterfat_percent"] == pytest.approx(4.43)
    assert quality["protein_percent"] == pytest.approx(3.14)
    assert quality["lactose_percent"] == pytest.approx(4.62)
    assert quality["scc"] == 249
    assert quality["tbc"] == 10


# ---------------------------------------------------------------------------
# 6: adapter does not mutate the source model
# ---------------------------------------------------------------------------

def test_adapter_does_not_mutate_source_statement(strathroy_statement):
    before = strathroy_statement.model_dump()
    adapt_dairy_statement_to_monthly_entry(strathroy_statement)
    after = strathroy_statement.model_dump()
    assert before == after


# ---------------------------------------------------------------------------
# 7: no revenue double-counted
# ---------------------------------------------------------------------------

def test_revenue_is_not_double_counted(monthly_entry):
    revenue = monthly_entry["revenue"]
    assert revenue["milk"] == revenue["total"]
    assert revenue["cattle_sales"] == 0
    assert revenue["lamb_sales"] == 0
    assert revenue["wool"] == 0
    assert revenue["other"] == 0


def test_aggregated_revenue_not_double_counted(monthly_entry):
    farm = _fake_dairy_only_farm(monthly_entry)
    filtered = filter_farm_by_sectors(farm, ["dairy"])
    aggregated = aggregate_sector_financials(filtered)
    totals = aggregated["revenue_totals"]
    assert totals["milk"] == pytest.approx(totals["total"])


# ---------------------------------------------------------------------------
# 8: existing dataset is untouched
# ---------------------------------------------------------------------------

def test_existing_dataset_sectors_unaffected(monthly_entry):
    """Running the full mock -> adapter -> aggregation flow must never touch the real dataset file."""
    before = load_multi_sector_farm(MULTI_SECTOR_FILE)
    before_counts = {
        sector: len(before["sectors"][sector]["monthly"])
        for sector in ("dairy", "beef", "lamb")
    }

    farm = _fake_dairy_only_farm(monthly_entry)
    filtered = filter_farm_by_sectors(farm, ["dairy"])
    aggregate_sector_financials(filtered)

    after = load_multi_sector_farm(MULTI_SECTOR_FILE)
    for sector, count_before in before_counts.items():
        assert len(after["sectors"][sector]["monthly"]) == count_before


# ---------------------------------------------------------------------------
# 9-10: existing validation/error behaviour untouched
# ---------------------------------------------------------------------------

def test_unsupported_provider_still_raises_domain_error():
    with pytest.raises(UnsupportedDairyProviderError):
        MockDairyStatementProvider().get_milk_statement(
            provider_id="UNSUPPORTED_PROVIDER",
            supplier_no=_SUPPLIER_NO,
            invoice_id=_INVOICE_ID,
            month_no=_MONTH_NO,
            year=_YEAR,
        )


def test_invalid_month_still_rejected_by_contract_model():
    with pytest.raises(Exception):
        MockDairyStatementProvider().get_milk_statement(
            provider_id=_PROVIDER_ID,
            supplier_no=_SUPPLIER_NO,
            invoice_id=_INVOICE_ID,
            month_no=13,
            year=_YEAR,
        )


# ---------------------------------------------------------------------------
# Financial consistency check (documented, not forced)
# ---------------------------------------------------------------------------

def test_financial_consistency_between_rate_and_authoritative_total(strathroy_statement, monthly_entry):
    """
    38,804 litres x 0.37419 EUR/litre = 14,520.06876 EUR (the rate-derived figure).
    The statement's actual total_payment is 14,476.66 EUR.

    These two figures are deliberately NOT forced to match. gross_price_ppl is
    the approved source for the *effective rate*; total_payment is authoritative
    for the *amount actually paid*. The ~43.41 EUR gap between them is expected
    -- it is exactly what bonuses, deductions, VAT, or other adjustments would
    produce on a real statement. The adapter's job is to preserve both figures
    faithfully and independently, not to reconcile them.
    """
    litres = Decimal(str(monthly_entry["operational"]["milk_litres"]))
    rate = strathroy_statement.pricing.gross_price_ppl / Decimal("100")
    rate_derived_amount = litres * rate

    actual_total_payment = strathroy_statement.pricing.total_payment

    assert rate_derived_amount == Decimal("14520.06876")
    assert actual_total_payment == Decimal("14476.66")
    assert rate_derived_amount != actual_total_payment

    # The adapter must use the authoritative figure, never the rate-derived one.
    assert Decimal(str(monthly_entry["revenue"]["milk"])) == actual_total_payment
