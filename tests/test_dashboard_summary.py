"""Unit tests for executive dashboard summary helpers."""

from __future__ import annotations

import pytest

import services.financial_record_service as record_svc
from models.multi_sector_farm import compute_household_month
from services.dashboard_summary import (
    build_cash_position_series,
    build_current_period_summary,
    build_overview_chart_data,
    build_overview_summary,
    calculate_dashboard_kpis,
    calculate_sector_performance,
    compute_actual_cash_flow,
    dataset_coverage_cutoff,
    generate_dashboard_alerts,
    get_budget_entries,
    get_historical_data,
    get_selected_sector_data,
    sector_status_label,
    sum_loan_principal,
    sum_outstanding_debt,
)


@pytest.fixture(autouse=True)
def isolated_records_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(record_svc, "FINANCIAL_RECORDS_DIR", str(tmp_path))
    yield tmp_path


def test_sector_status_label():
    assert sector_status_label(["dairy", "beef", "lamb"]) == "Combined Overview"
    assert sector_status_label(["dairy"]) == "Dairy Only"
    assert sector_status_label(["dairy", "lamb"]) == "Dairy + Lamb Overview"


def test_sum_loan_principal():
    summary = {"loans": [{"principal": 185000}, {"principal": 35000}]}
    assert sum_loan_principal(summary) == 220000


def test_get_selected_sector_data_beef_only():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["beef"])
    assert filtered["selected_sectors"] == ["beef"]
    assert "dairy" not in filtered.get("sectors", {})


def test_calculate_dashboard_kpis_six_cards():
    summary = {"annual_revenue": 1000000, "annual_profit": 150000, "profit_margin": 15.0}
    farm = {"opening_cash_balance": 28500, "_loans": [{"principal": 220000}]}
    monthly = [{"running_balance": 42000}]
    cards = calculate_dashboard_kpis(summary, farm, monthly, "Low")
    assert len(cards) == 6
    ids = [c["id"] for c in cards]
    assert ids == [
        "revenue", "operating_profit", "cash_available",
        "debt_outstanding", "profit_margin", "risk_rating",
    ]
    # No debt register supplied: falls back to summed loan principal.
    assert cards[3]["value"] == "€220,000"
    # Phase 10: every KPI card names the time window it covers.
    for card in cards:
        assert "period_type" in card["period"]
    ttm_ids = {"revenue", "operating_profit", "profit_margin"}
    point_in_time_ids = {"cash_available", "debt_outstanding", "risk_rating"}
    for card in cards:
        if card["id"] in ttm_ids:
            assert card["period"]["period_type"] == "Trailing 12 Months"
        elif card["id"] in point_in_time_ids:
            assert card["period"]["period_type"] == "Point in Time"


def test_calculate_dashboard_kpis_prefers_debt_register():
    summary = {"annual_revenue": 1000000, "annual_profit": 150000, "profit_margin": 15.0}
    farm = {
        "opening_cash_balance": 28500,
        "_loans": [{"principal": 220000}],
        "_debt_register": [{"outstanding_balance": 95000}, {"outstanding_balance": 15000}],
    }
    cards = calculate_dashboard_kpis(summary, farm, [], "Low")
    assert cards[3]["value"] == "€110,000"


def test_build_overview_summary_no_alerts_is_reassuring():
    farm = {"opening_cash_balance": 28500}
    monthly_forecast = [
        {"month": m, "combined_running_balance": 10000 + m * 100, "combined_cashflow": 100}
        for m in range(1, 13)
    ]
    alerts = [{
        "message": "No critical alerts — farm metrics look stable.",
        "severity": "info",
        "what": "No critical alerts",
        "review": "No action needed — recheck after your next analysis run.",
    }]
    summary = build_overview_summary(farm, monthly_forecast, alerts)
    assert summary["current_cash_position"]["value"] == "€28,500"
    assert summary["lowest_projected_cash_balance"]["month"] == 1
    assert summary["lowest_projected_cash_balance"]["is_deficit"] is False
    assert summary["projected_annual_cashflow"]["value"] == "€1,200"
    assert "No critical concerns" in summary["main_financial_concern"]
    assert "No action needed" in summary["recommended_next_action"]


def test_build_overview_summary_surfaces_top_alert():
    farm = {"opening_cash_balance": 5000}
    monthly_forecast = [
        {"month": 1, "combined_running_balance": 4000, "combined_cashflow": -1000},
        {"month": 2, "combined_running_balance": -2000, "combined_cashflow": -6000},
        {"month": 3, "combined_running_balance": 500, "combined_cashflow": 2500},
    ]
    alerts = [{
        "message": "Cash-flow warning: the forecast shows a negative cash balance in month 2.",
        "severity": "high",
        "what": "Future months show a negative cash balance",
        "review": "Plan ahead for the shortfall — bring forward income, defer costs, or arrange short-term credit.",
    }]
    summary = build_overview_summary(farm, monthly_forecast, alerts)
    assert summary["lowest_projected_cash_balance"]["month"] == 2
    assert summary["lowest_projected_cash_balance"]["is_deficit"] is True
    assert summary["projected_annual_cashflow"]["is_deficit"] is True
    assert summary["main_financial_concern"] == "Future months show a negative cash balance"
    assert "bring forward income" in summary["recommended_next_action"]


def test_build_overview_summary_handles_empty_forecast():
    summary = build_overview_summary({"opening_cash_balance": 1000}, [], [])
    assert summary["main_financial_concern"].startswith("Not enough data")


def test_latest_period_finds_most_recent_across_sectors():
    from services.dashboard_summary import _latest_period

    filtered = {
        "sectors": {
            "dairy": {"monthly": [{"period": "2024-01"}, {"period": "2025-12"}]},
            "beef": {"monthly": [{"period": "2024-06"}]},
        }
    }
    assert _latest_period(filtered) == "2025-12"
    assert _latest_period({"sectors": {}}) is None


def test_sum_outstanding_debt():
    register = [{"outstanding_balance": 1000}, {"outstanding_balance": 2500.5}]
    assert sum_outstanding_debt(register) == 3500.5
    assert sum_outstanding_debt(None) == 0
    assert sum_outstanding_debt([]) == 0


def test_calculate_sector_performance_selected_only():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef"])
    rows = calculate_sector_performance(filtered)
    assert len(rows) == 2
    sectors = {r["sector"] for r in rows}
    assert sectors == {"dairy", "beef"}
    for row in rows:
        assert row["revenue"] > 0
        assert "margin_pct" in row
        assert row["status"] in ("Good", "Fair", "Watch")
        assert row["period"]["period_type"] == "Trailing 12 Months"


def test_build_overview_chart_24_months():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    chart = build_overview_chart_data(filtered, months=24)
    assert len(chart) <= 24
    assert len(chart) >= 12
    assert "revenue" in chart[0]
    assert "costs" in chart[0]


def test_generate_dashboard_alerts_max_five():
    farm = {"opening_cash_balance": 500, "feed": 500000}
    summary = {"annual_revenue": 1000000, "annual_profit": -5000, "annual_costs": 1005000}
    kpis = {"monthly_cashflow": -500}
    alerts = generate_dashboard_alerts(farm, summary, kpis, limit=5)
    assert len(alerts) <= 5
    assert all("message" in a for a in alerts)


def test_generate_dashboard_alerts_max_five_has_rich_fields():
    farm = {"opening_cash_balance": 500, "feed": 500000}
    summary = {"annual_revenue": 1000000, "annual_profit": -5000, "annual_costs": 1005000}
    kpis = {"monthly_cashflow": -500}
    alerts = generate_dashboard_alerts(farm, summary, kpis, limit=5)
    assert len(alerts) <= 5
    for alert in alerts:
        assert set(("message", "severity", "priority", "what", "when", "cause", "review")) <= set(alert.keys())
        assert alert["what"]
        assert alert["cause"]
        assert alert["review"]
        assert alert["when"]


def test_generate_dashboard_alerts_no_alerts_case_has_rich_fields():
    farm = {"opening_cash_balance": 100000, "feed": 1000}
    summary = {"annual_revenue": 1000000, "annual_profit": 500000, "annual_costs": 500000}
    kpis = {"monthly_cashflow": 10000}
    alerts = generate_dashboard_alerts(farm, summary, kpis, limit=5)
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "info"
    assert alerts[0]["what"]
    assert alerts[0]["cause"]
    assert alerts[0]["review"]


def test_generate_dashboard_alerts_when_extracts_month_span():
    farm = {"opening_cash_balance": 5000, "feed": 5000}
    summary = {"annual_revenue": 100000, "annual_profit": 20000, "annual_costs": 80000}
    kpis = {"monthly_cashflow": 500}
    monthly_forecast = [
        {"month": 1, "combined_running_balance": 1000},
        {"month": 2, "combined_running_balance": -500},
        {"month": 3, "combined_running_balance": -1500},
    ]
    alerts = generate_dashboard_alerts(farm, summary, kpis, monthly_forecast=monthly_forecast)
    cashflow_alert = next(a for a in alerts if "Cash-flow warning" in a["message"])
    assert cashflow_alert["when"] == "Months 2-3"
    assert "negative cash balance" in cashflow_alert["cause"].lower() or cashflow_alert["cause"]


def test_generate_dashboard_alerts_annual_alert_when_is_generic():
    farm = {"opening_cash_balance": 500, "feed": 500000}
    summary = {"annual_revenue": 1000000, "annual_profit": -5000, "annual_costs": 1005000}
    kpis = {"monthly_cashflow": -500}
    alerts = generate_dashboard_alerts(farm, summary, kpis)
    profit_alert = next(a for a in alerts if "Negative profit" in a["message"])
    assert profit_alert["when"] == "Across the current 12-month forecast"


def test_generate_dashboard_alerts_includes_early_cashflow_warnings():
    farm = {"opening_cash_balance": 5000, "feed": 5000}
    summary = {"annual_revenue": 100000, "annual_profit": 20000, "annual_costs": 80000}
    kpis = {"monthly_cashflow": 500}
    monthly_forecast = [
        {"month": 1, "combined_running_balance": 1000},
        {"month": 2, "combined_running_balance": -500},
        {"month": 3, "combined_running_balance": -1500},
        {"month": 4, "combined_running_balance": -3000},
    ]
    debt_register = [{"lender": "Bank", "monthly_repayment": 400}]
    alerts = generate_dashboard_alerts(
        farm, summary, kpis, monthly_forecast=monthly_forecast, debt_register=debt_register,
    )
    messages = " | ".join(a["message"] for a in alerts)
    assert "Increasing overdraft use" in messages
    assert "Cash-flow warning" in messages
    assert all(a["severity"] in ("high", "medium", "low") for a in alerts)


def test_compute_actual_cash_flow_and_budget_entries_available_from_dashboard_summary():
    """These moved from cashflow_budget_service (P0.1 refactor) so the
    Overview can reuse the exact same "actual" definition without a
    circular import; verify they still work from their new home."""
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    farm_summary = filtered.get("farm_summary") or {}
    actual = compute_actual_cash_flow(filtered, farm_summary, months=3)
    assert len(actual) == 3
    for entry in actual.values():
        assert entry["actual_cash_in"] >= 0
        assert "actual_net" in entry
    budget_entries = get_budget_entries(filtered)
    assert len(budget_entries) > 0
    years_months = [(e["year"], e["month"]) for e in budget_entries]
    assert years_months == sorted(years_months)


FARM = "multi_sector_farm.json"


def test_dataset_coverage_cutoff_is_last_dataset_month():
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    cutoff = dataset_coverage_cutoff(filtered)
    assert cutoff == (2025, 12)


def test_compute_actual_cash_flow_ignores_manual_record_inside_dataset_coverage():
    """P0.4: a manual record dated inside the dataset's own covered window
    must not be added on top of it - the dataset's monthly figures are
    already a complete total for that month, so adding a manual record too
    would double-count it."""
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    farm_summary = filtered.get("farm_summary") or {}
    without_manual = compute_actual_cash_flow(filtered, farm_summary, months=12)

    record_svc.add_financial_record(FARM, {
        "record_type": "expense", "date": "2025-06-15", "category": "feed",
        "amount": 5000.0, "description": "Extra feed", "counterparty": None,
        "notes": None, "sector": None,
    })
    with_manual = compute_actual_cash_flow(filtered, farm_summary, months=12, farm_file=FARM)
    assert with_manual[(2025, 6)]["actual_cash_out"] == without_manual[(2025, 6)]["actual_cash_out"]
    assert len(with_manual) == len(without_manual)


def test_compute_actual_cash_flow_adds_manual_record_after_dataset_coverage():
    """A manual record dated after the dataset's last covered month is
    genuinely new activity - the dataset has no figure for it at all, so it
    is safe to add in full, and it extends "actual" into a new month."""
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    farm_summary = filtered.get("farm_summary") or {}
    without_manual = compute_actual_cash_flow(filtered, farm_summary, months=12)
    assert (2026, 1) not in without_manual

    record_svc.add_financial_record(FARM, {
        "record_type": "income", "date": "2026-01-10", "category": "milk",
        "amount": 8000.0, "description": "Milk cheque", "counterparty": None,
        "notes": None, "sector": "dairy",
    })
    with_manual = compute_actual_cash_flow(filtered, farm_summary, months=12, farm_file=FARM)
    assert (2026, 1) in with_manual
    # Recurring household income/outgoings still apply to a manual-only
    # month (they are calendar-month recurring figures, not part of the
    # dataset's per-sector monthly line items) - the milk cheque is on top.
    household_jan = compute_household_month((farm_summary or {}).get("household") or {}, 1)
    assert with_manual[(2026, 1)]["actual_cash_in"] == round(8000.0 + household_jan["income"], 2)


def test_build_current_period_summary_advances_with_new_manual_records():
    filtered = get_selected_sector_data(FARM, ["dairy", "beef", "lamb"])
    without_manual = build_current_period_summary(filtered)
    assert without_manual["period"]["label"] == "Dec 2025"

    record_svc.add_financial_record(FARM, {
        "record_type": "income", "date": "2026-01-10", "category": "milk",
        "amount": 8000.0, "description": "Milk cheque", "counterparty": None,
        "notes": None, "sector": "dairy",
    })
    with_manual = build_current_period_summary(filtered, farm_file=FARM)
    assert with_manual["period"]["label"] == "Jan 2026"


def test_build_current_period_summary_returns_latest_actual_month():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    result = build_current_period_summary(filtered)
    assert result is not None
    assert result["period"]["period_type"] == "Historical Actual"
    assert result["income"].startswith("€") or result["income"].startswith("-€")
    assert result["costs"].startswith("€") or result["costs"].startswith("-€")
    assert isinstance(result["is_deficit"], bool)


def test_build_current_period_summary_none_without_data():
    assert build_current_period_summary(None) is None
    assert build_current_period_summary({}) is None


def test_build_cash_position_series_history_reconciles_to_opening_balance():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    farm_summary = filtered.get("farm_summary") or {}
    opening = float(farm_summary.get("opening_cash_balance") or 0)
    series = build_cash_position_series(filtered, {"opening_cash_balance": opening}, [], history_months=6)
    assert series is not None
    history = series["history"]
    assert len(history) == 6
    # Most recent historical month's closing balance is today's real opening balance.
    assert history[-1]["closing_balance"] == round(opening, 2)
    # Each month's closing balance must reconcile with the previous month's
    # closing balance plus that month's own real net cash flow (no invented figures).
    for i in range(1, len(history)):
        prev_balance = history[i - 1]["closing_balance"]
        assert round(prev_balance + history[i]["net_cashflow"], 2) == history[i]["closing_balance"]
    assert series["current_balance"] == round(opening, 2)
    assert series["forecast"] == []


def test_build_cash_position_series_forecast_segment_uses_running_balance():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy"])
    monthly_forecast = [
        {"month": 1, "combined_running_balance": 1000, "combined_cashflow": 200},
        {"month": 2, "combined_running_balance": 1200, "combined_cashflow": 200},
    ]
    series = build_cash_position_series(filtered, {"opening_cash_balance": 800}, monthly_forecast, history_months=3)
    assert [pt["series"] for pt in series["forecast"]] == ["forecast", "forecast"]
    assert series["forecast"][0]["closing_balance"] == 1000
    assert series["forecast"][0]["label"] == "Jan"
    assert series["forecast"][1]["label"] == "Feb"
    # Forecast points never carry a budget reference (Actual/Budget/Forecast stay distinguishable).
    assert all(pt["budget_net"] is None for pt in series["forecast"])


def test_build_cash_position_series_none_without_filtered_raw():
    assert build_cash_position_series(None, {"opening_cash_balance": 100}, []) is None


def test_build_overview_summary_includes_current_period_and_cash_position():
    filtered = get_selected_sector_data("multi_sector_farm.json", ["dairy", "beef", "lamb"])
    farm_summary = filtered.get("farm_summary") or {}
    farm = {"opening_cash_balance": farm_summary.get("opening_cash_balance", 0)}
    monthly_forecast = [
        {"month": m, "combined_running_balance": 10000 + m * 100, "combined_cashflow": 100}
        for m in range(1, 13)
    ]
    alerts = [{
        "message": "No critical alerts — farm metrics look stable.",
        "severity": "info",
        "what": "No critical alerts",
        "review": "No action needed — recheck after your next analysis run.",
    }]
    summary = build_overview_summary(
        farm, monthly_forecast, alerts,
        forecast_summary={"annual_profit": 45000}, filtered_raw=filtered,
    )
    assert summary["current_period"] is not None
    assert summary["expected_annual_farm_profit"]["value"] == "€45,000"
    assert summary["expected_annual_farm_profit"]["is_deficit"] is False
    assert summary["cash_position"] is not None
    assert len(summary["cash_position"]["history"]) == 6
    assert len(summary["cash_position"]["forecast"]) == 12


def test_build_overview_summary_still_works_without_filtered_raw():
    """Backward compatibility: callers that don't pass filtered_raw/forecast_summary
    (e.g. existing tests above) must keep getting the original fields untouched."""
    farm = {"opening_cash_balance": 28500}
    monthly_forecast = [
        {"month": m, "combined_running_balance": 10000 + m * 100, "combined_cashflow": 100}
        for m in range(1, 13)
    ]
    summary = build_overview_summary(farm, monthly_forecast, [])
    assert summary["current_period"] is None
    assert summary["cash_position"] is None
    assert summary["expected_annual_farm_profit"]["value"] == "—"


def test_get_historical_data():
    data = get_historical_data("multi_sector_farm.json", ["lamb"])
    assert data["success"] is True
    assert data["selected_sectors"] == ["lamb"]
    assert len(data["sectors"]) == 1
    assert len(data["combined_monthly"]) >= 12
