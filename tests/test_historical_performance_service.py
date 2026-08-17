"""Tests for Previous Performance year-over-year comparison (P1.5).

Uses the real multi_sector_farm.json dataset (2024-2025, 12 months each)
so the full-year comparison exercises real data, then layers manual
FinancialRecords for 2026 (via the isolated FINANCIAL_RECORDS_DIR) to
exercise the partial-year "same months" comparison path.
"""

from __future__ import annotations

import pytest

import services.financial_record_service as record_svc
from services.financial_record_service import add_financial_record
from services.historical_performance_service import build_year_over_year_comparison

FARM = "multi_sector_farm.json"
SECTORS = ["dairy", "beef", "lamb"]


@pytest.fixture(autouse=True)
def isolated_records_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(record_svc, "FINANCIAL_RECORDS_DIR", str(tmp_path))
    yield tmp_path


def test_full_years_present_for_dataset_coverage():
    result = build_year_over_year_comparison(FARM, SECTORS)
    years = {row["year"]: row for row in result["years"]}

    assert set(years.keys()) == {2024, 2025}
    for row in years.values():
        assert row["months_covered"] == 12
        assert row["is_partial"] is False


def test_full_year_comparison_matches_manual_totals():
    result = build_year_over_year_comparison(FARM, SECTORS)
    years = {row["year"]: row for row in result["years"]}
    comparisons = {c["year"]: c for c in result["comparisons"]}

    assert 2025 in comparisons
    comp = comparisons[2025]
    assert comp["previous_year"] == 2024
    assert comp["basis"] == "full_year"
    assert "note" not in comp

    for metric in ("income", "costs", "farm_profit", "cash_generated"):
        assert comp[metric]["current"] == years[2025][metric]
        assert comp[metric]["previous"] == years[2024][metric]
        assert comp[metric]["change"] == pytest.approx(years[2025][metric] - years[2024][metric])

    # 2024 has no prior year in the dataset, so no comparison for it.
    assert 2024 not in comparisons


def test_partial_current_year_compares_like_for_like_months():
    # Only Jan/Feb 2026 recorded so far.
    add_financial_record(FARM, {
        "record_type": "income", "date": "2026-01-15", "category": "milk",
        "amount": 5000, "description": "Jan milk cheque",
    })
    add_financial_record(FARM, {
        "record_type": "expense", "date": "2026-02-10", "category": "feed",
        "amount": 2000, "description": "Feb feed",
    })

    result = build_year_over_year_comparison(FARM, SECTORS)
    years = {row["year"]: row for row in result["years"]}
    comparisons = {c["year"]: c for c in result["comparisons"]}

    assert years[2026]["is_partial"] is True
    assert years[2026]["months_covered"] == 2

    assert 2026 in comparisons
    comp = comparisons[2026]
    assert comp["previous_year"] == 2025
    assert comp["basis"] == "same_months_partial"
    assert "2 month(s)" in comp["note"]

    # The 2025 side of the comparison must be restricted to Jan+Feb 2025
    # only, never the full-year 2025 total.
    assert comp["income"]["previous"] != years[2025]["income"]
    assert comp["income"]["current"] == 5000
    assert comp["costs"]["current"] == 2000


def test_no_data_returns_empty_years_and_comparisons(monkeypatch):
    import services.historical_performance_service as hist_svc

    monkeypatch.setattr(hist_svc, "get_sector_monthly_history", lambda filtered, months=10_000: ([], {}))
    monkeypatch.setattr(hist_svc, "compute_actual_cash_flow", lambda *a, **k: {})
    result = build_year_over_year_comparison(FARM, SECTORS)
    assert result["years"] == []
    assert result["comparisons"] == []


def test_selected_sectors_reflected_in_response():
    result = build_year_over_year_comparison(FARM, ["dairy"])
    assert result["selected_sectors"] == ["dairy"]
