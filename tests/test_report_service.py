"""Tests for PDF report generation (P2.3), focused on the new
"Accountant / Advisor Summary" report type.

Uses the real `multi_sector_farm.json` dataset (as the other API-level
tests do) since `collect_report_data` composes many existing, already
farm-file-based services. Report PDFs are written to `config.paths.REPORTS_DIR`,
redirected to a pytest tmp_path so a test run never leaves files behind in
the real outputs/ directory.
"""

from __future__ import annotations

import os

import pytest

import services.report_service as report_service

FARM = "multi_sector_farm.json"
SECTORS = ["dairy", "beef", "lamb"]


@pytest.fixture(autouse=True)
def isolated_reports_dir(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(report_service, "REPORTS_DIR", str(reports_dir))
    # ensure_output_dirs() only creates the real config.paths.REPORTS_DIR,
    # not this patched path, so the directory is created directly above.
    yield tmp_path


def test_accountant_report_is_a_registered_type():
    assert "accountant" in report_service.REPORT_TYPES
    assert "accountant" in report_service.PAGE_SETS


def test_collect_report_data_includes_actuals_budget_loans_and_yoy_sections():
    data = report_service.collect_report_data(FARM, "accountant", sectors=SECTORS)

    ie = data["income_expense_actual"]
    assert ie["success"] is True
    assert "income_total" in ie and "expense_total" in ie

    bv = data["budget_variance"]
    assert bv["success"] is True
    assert "overall_status" in bv

    loans = data["loans_summary"]
    assert "total_outstanding_debt" in loans
    assert "total_annual_repayments" in loans

    yoy = data["year_over_year"]
    assert yoy["success"] is True
    assert isinstance(yoy["years"], list)

    assert data["is_sample_data"] is True
    meeting = data["meeting"]
    assert isinstance(meeting["cash_now"], (int, float))
    assert isinstance(meeting["actual_net"], (int, float))
    assert isinstance(meeting["lowest_cash"], (int, float))
    assert isinstance(meeting["total_debt"], (int, float))
    assert "Sheep" in meeting["enterprises"]
    assert data["monte_carlo"] == {}
    assert data["sector_performance"]
    assert any(row.get("label") == "Sheep" or row.get("sector") == "lamb" for row in data["sector_performance"])
    assert (data.get("milk_down") or {}).get("comparison")


def test_get_report_preview_for_accountant_report():
    preview = report_service.get_report_preview(FARM, "accountant", sectors=SECTORS)
    assert preview["success"] is True
    assert preview["report_type"] == "accountant"
    assert preview["sections"] == report_service.PAGE_SETS["accountant"]
    cards = preview["preview_kpis"]
    assert len(cards) == 4
    for card in cards:
        assert card["kind"] == "currency"
        assert isinstance(card["value"], (int, float))


def test_generate_accountant_report_produces_a_pdf_file():
    result = report_service.generate_farmer_report(FARM, "accountant", sectors=SECTORS)
    assert result["success"] is True
    assert result["report_type"] == "accountant"

    filepath = os.path.join(report_service.REPORTS_DIR, result["filename"])
    assert os.path.exists(filepath)
    assert os.path.getsize(filepath) > 0
    cards = result["preview_kpis"]
    assert len(cards) == 4
    for card in cards:
        assert card["kind"] == "currency"
        assert isinstance(card["value"], (int, float))


def test_accountant_page_set_is_a_meeting_pack_not_monte_carlo():
    pages = report_service.PAGE_SETS["accountant"]
    assert "meeting" in pages
    assert "farm_position" in pages
    assert pages.index("farm_position") == pages.index("meeting") + 1
    assert "cash_forecast" in pages
    assert "milk_down" in pages
    assert "sector_contribution" in pages
    assert "loans_finance" in pages
    for excluded in ("monte_carlo", "investment", "advisor", "executive"):
        assert excluded not in pages


def test_loans_register_includes_rate_and_maturity():
    data = report_service.collect_report_data(FARM, "accountant", sectors=SECTORS)
    loans = data["loans_summary"]["loans"]
    assert loans
    assert loans[0].get("rate") is not None
    assert loans[0].get("maturity")
    assert loans[0].get("principal") is not None


def test_farm_position_uses_knockrow_sample_records():
    data = report_service.collect_report_data(FARM, "accountant", sectors=SECTORS)
    pos = data["farm_position"]
    assert pos["debtors"] == 14200
    assert pos["creditors"] == 19600
    assert pos["household"].get("drawings_monthly") == 2200
    assert pos["stock"].get("ewes") == 228
    assert pos["legal_name"]
    assert data["lowest_cash"]["month_label"] in report_service._CALENDAR_MONTHS
    assert "principal" in data["loans_summary"]["loans"][0]


def test_cover_identity_does_not_repeat_farm_name_or_county():
    data = report_service.collect_report_data(FARM, "accountant", sectors=SECTORS)
    lines = report_service._cover_identity_lines(data)
    assert lines[0] == "Knockrow Mixed Farm Ltd"
    assert "Knockrow Mixed Farm" not in lines
    assert "Tipperary" not in lines
    styles = report_service._styles()
    for key in ("cover_title", "cover_sub", "cover_farm", "cover_sample"):
        style = styles[key]
        assert style.leading >= style.fontSize


def test_unbudgeted_categories_never_show_a_fabricated_variance_in_the_pdf_data():
    data = report_service.collect_report_data(FARM, "accountant", sectors=SECTORS)
    for row in data["budget_variance"].get("unbudgeted_categories", []):
        assert row["status"] == "no_budget_set"
        assert row["difference"] is None
