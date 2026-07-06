"""
Multi-sector farm loader and adapter.

Converts multi_sector_farm.json + selected sectors into a legacy flat dict
compatible with the existing dairy-oriented forecast engine.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from config.paths import DATASETS_DIR
from models.multi_sector_farm import (
    DEFAULT_SECTORS,
    MULTI_SECTOR_FILE,
    SECTOR_LABELS,
    VALID_SECTORS,
)

COST_TO_LEGACY = {
    "feed": "feed",
    "fertiliser": "fertiliser",
    "vet": "vet",
    "breeding": "vet",
    "labour": "labour",
    "machinery": "contractor",
    "fuel": "fuel",
    "insurance": "insurance",
    "rent_land_lease": "contractor",
    "contractor": "contractor",
    "animal_purchases": "contractor",
    "housing": "contractor",
    "equipment": "contractor",
}

LEGACY_COST_FIELDS = (
    "feed",
    "fertiliser",
    "vet",
    "contractor",
    "labour",
    "insurance",
    "loan_repayments",
    "fuel",
    "electricity",
)


def _read_farm_json(farm_file: str) -> dict:
    path = os.path.join(DATASETS_DIR, farm_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Farm file not found: {farm_file}")
    with open(path, "r", encoding="utf-8") as fh:
        farm = json.load(fh)
    if not isinstance(farm, dict) or "farm_name" not in farm:
        raise ValueError(f"Farm file is missing required fields: {farm_file}")
    return farm


def is_multi_sector(farm: dict) -> bool:
    return farm.get("schema_version") == "2.0" and isinstance(farm.get("sectors"), dict)


def load_multi_sector_farm(farm_file: str = MULTI_SECTOR_FILE) -> dict:
    farm = _read_farm_json(farm_file)
    if not is_multi_sector(farm):
        raise ValueError(f"Not a multi-sector farm file: {farm_file}")
    return farm


def get_available_sectors(farm: dict) -> list[str]:
    if not is_multi_sector(farm):
        return []
    configured = farm.get("available_sectors") or list(farm.get("sectors", {}).keys())
    return [s for s in configured if s in VALID_SECTORS]


def normalize_sectors(sectors: list[str] | None, farm: dict | None = None) -> list[str]:
    available = get_available_sectors(farm) if farm else list(DEFAULT_SECTORS)
    if not sectors:
        return available or list(DEFAULT_SECTORS)
    cleaned = []
    for sector in sectors:
        key = sector.strip().lower()
        if key in VALID_SECTORS and key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        raise ValueError("At least one sector must be selected.")
    return cleaned


def parse_sectors_param(sectors: str | list[str] | None, farm: dict | None = None) -> list[str]:
    if sectors is None:
        return normalize_sectors(None, farm)
    if isinstance(sectors, str):
        parts = [part.strip() for part in sectors.split(",") if part.strip()]
        return normalize_sectors(parts, farm)
    return normalize_sectors(list(sectors), farm)


def filter_farm_by_sectors(farm: dict, sectors: list[str]) -> dict:
    if not is_multi_sector(farm):
        return farm
    selected = normalize_sectors(sectors, farm)
    filtered_sectors = {
        key: farm["sectors"][key]
        for key in selected
        if key in farm.get("sectors", {})
    }
    return {
        **farm,
        "selected_sectors": selected,
        "sectors": filtered_sectors,
    }


def _trailing_months(monthly: list[dict], count: int = 12) -> list[dict]:
    if not monthly:
        return []
    return monthly[-count:]


def _sum_costs(entries: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for entry in entries:
        for key, value in (entry.get("costs") or {}).items():
            if key == "total":
                continue
            legacy_key = COST_TO_LEGACY.get(key, "contractor")
            totals[legacy_key] += float(value or 0)
    return dict(totals)


def _sum_revenue(entries: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for entry in entries:
        rev = entry.get("revenue") or {}
        for key in ("milk", "cattle_sales", "lamb_sales", "wool", "other"):
            totals[key] += float(rev.get(key) or 0)
        totals["total"] += float(rev.get("total") or 0)
    return dict(totals)


def aggregate_sector_financials(filtered: dict) -> dict:
    """Aggregate trailing-12-month financials for selected sectors."""
    sector_months: dict[str, list[dict]] = {}
    for sector_id, sector_data in (filtered.get("sectors") or {}).items():
        sector_months[sector_id] = _trailing_months(sector_data.get("monthly") or [])

    combined_monthly: dict[tuple[int, int], dict] = defaultdict(lambda: {"revenue": 0.0, "costs": 0.0})
    all_entries: list[dict] = []
    revenue_totals: dict[str, float] = defaultdict(float)
    cost_totals: dict[str, float] = defaultdict(float)

    dairy_entries: list[dict] = []
    beef_entries: list[dict] = []
    lamb_entries: list[dict] = []

    for sector_id, entries in sector_months.items():
        all_entries.extend(entries)
        rev = _sum_revenue(entries)
        costs = _sum_costs(entries)
        for key, value in rev.items():
            revenue_totals[key] += value
        for key, value in costs.items():
            cost_totals[key] += value
        if sector_id == "dairy":
            dairy_entries = entries
        elif sector_id == "beef":
            beef_entries = entries
        elif sector_id == "lamb":
            lamb_entries = entries

        for entry in entries:
            key = (entry.get("year"), entry.get("month"))
            combined_monthly[key]["revenue"] += float((entry.get("revenue") or {}).get("total") or 0)
            combined_monthly[key]["costs"] += float((entry.get("costs") or {}).get("total") or 0)

    dairy_cows = 0.0
    dairy_litres = 0.0
    milk_revenue = 0.0
    if dairy_entries:
        dairy_cows = sum((e.get("operational") or {}).get("milking_cows", 0) for e in dairy_entries) / len(dairy_entries)
        dairy_litres = sum((e.get("operational") or {}).get("milk_litres", 0) for e in dairy_entries)
        milk_revenue = revenue_totals.get("milk", 0)
    litres_per_cow = (dairy_litres / dairy_cows) if dairy_cows else 0
    milk_price = (milk_revenue / dairy_litres) if dairy_litres else 0

    beef_cattle = 0.0
    beef_price = 0.0
    if beef_entries:
        beef_cattle = sum((e.get("operational") or {}).get("cattle_on_farm", 0) for e in beef_entries) / len(beef_entries)
        prices = [(e.get("pricing") or {}).get("beef_sale_price_per_head") for e in beef_entries if (e.get("pricing") or {}).get("beef_sale_price_per_head")]
        beef_price = sum(prices) / len(prices) if prices else 0

    lamb_ewes = 0.0
    lamb_price = 0.0
    lambs_sold = 0
    if lamb_entries:
        lamb_ewes = sum((e.get("operational") or {}).get("ewes", 0) for e in lamb_entries) / len(lamb_entries)
        prices = [(e.get("pricing") or {}).get("lamb_price_per_kg") for e in lamb_entries if (e.get("pricing") or {}).get("lamb_price_per_kg")]
        lamb_price = sum(prices) / len(prices) if prices else 0
        lambs_sold = sum(int((e.get("operational") or {}).get("lambs_sold") or 0) for e in lamb_entries)

    other_revenue = (
        revenue_totals.get("cattle_sales", 0)
        + revenue_totals.get("lamb_sales", 0)
        + revenue_totals.get("wool", 0)
        + revenue_totals.get("other", 0)
    )
    if "dairy" not in filtered.get("selected_sectors", []):
        other_revenue += revenue_totals.get("milk", 0)

    loans = (filtered.get("farm_summary") or {}).get("loans") or []
    loan_repayments = sum(float(loan.get("monthly_repayment") or 0) for loan in loans) * 12

    return {
        "selected_sectors": filtered.get("selected_sectors", []),
        "revenue_totals": dict(revenue_totals),
        "cost_totals": cost_totals,
        "loan_repayments_annual": loan_repayments,
        "dairy": {
            "milking_cows": round(dairy_cows),
            "litres_per_cow": round(litres_per_cow * 12, 2) if dairy_cows else 0,
            "milk_price": round(milk_price, 4),
            "annual_milk_litres": round(dairy_litres, 0),
        },
        "beef": {
            "cattle_on_farm": round(beef_cattle),
            "avg_sale_price_per_head": round(beef_price, 2),
            "annual_cattle_sales_revenue": revenue_totals.get("cattle_sales", 0),
        },
        "lamb": {
            "ewes": round(lamb_ewes),
            "avg_lamb_price_per_kg": round(lamb_price, 2),
            "lambs_sold_trailing_12": lambs_sold,
            "annual_lamb_revenue": revenue_totals.get("lamb_sales", 0) + revenue_totals.get("wool", 0),
        },
        "other_revenue": round(other_revenue, 2),
        "combined_monthly": dict(combined_monthly),
        "trailing_entries": all_entries,
    }


def _build_monthly_forecast(farm: dict, aggregated: dict) -> list[dict]:
    """Build 12-month forward forecast from trailing calendar-month patterns."""
    combined = aggregated.get("combined_monthly") or {}
    by_calendar: dict[int, list[dict]] = defaultdict(list)
    for (year, month), values in combined.items():
        by_calendar[int(month)].append(values)

    scheme = farm.get("scheme_payments") or {}
    scheme_months = scheme.get("scheme_payment_months") or {}
    opening = float((farm.get("farm_summary") or {}).get("opening_cash_balance") or 0)
    running = opening
    forecast: list[dict] = []

    for month in range(1, 13):
        samples = by_calendar.get(month, [{"revenue": 0, "costs": 0}])
        avg_revenue = sum(s["revenue"] for s in samples) / len(samples)
        avg_costs = sum(s["costs"] for s in samples) / len(samples)
        monthly_revenue = avg_revenue
        if month == scheme_months.get("biss"):
            monthly_revenue += float(scheme.get("biss") or 0)
        if month == scheme_months.get("acres"):
            monthly_revenue += float(scheme.get("acres") or 0)
        if month == scheme_months.get("other_grants"):
            monthly_revenue += float(scheme.get("other_grants") or 0)
        loan_monthly = aggregated.get("loan_repayments_annual", 0) / 12
        monthly_costs = avg_costs + loan_monthly
        cashflow = monthly_revenue - monthly_costs
        running += cashflow
        forecast.append({
            "month": month,
            "revenue": round(monthly_revenue, 2),
            "costs": round(monthly_costs, 2),
            "cashflow": round(cashflow, 2),
            "running_balance": round(running, 2),
        })
    return forecast


def get_kpi_visibility(selected_sectors: list[str]) -> dict[str, bool]:
    return {
        "farm_level": True,
        "dairy": "dairy" in selected_sectors,
        "beef": "beef" in selected_sectors,
        "lamb": "lamb" in selected_sectors,
        "revenue_per_cow": "dairy" in selected_sectors,
        "profit_per_cow": "dairy" in selected_sectors,
        "milk_price": "dairy" in selected_sectors,
        "feed_cost_ratio": True,
        "beef_revenue_per_head": "beef" in selected_sectors,
        "lamb_revenue_per_ewe": "lamb" in selected_sectors,
    }


def list_sectors_for_selector(farm: dict, selected: list[str] | None = None) -> list[dict]:
    chosen = normalize_sectors(selected, farm) if selected else normalize_sectors(None, farm)
    result = []
    for sector_id in get_available_sectors(farm):
        sector = (farm.get("sectors") or {}).get(sector_id, {})
        result.append({
            "id": sector_id,
            "label": sector.get("display_name") or SECTOR_LABELS.get(sector_id, sector_id.title()),
            "selected": sector_id in chosen,
        })
    return result


def to_legacy_farm_dict(aggregated: dict, farm: dict) -> dict:
    """Produce a flat dict compatible with forecast_engine calculators."""
    scheme = farm.get("scheme_payments") or {}
    summary = farm.get("farm_summary") or {}
    costs = aggregated.get("cost_totals") or {}
    selected = aggregated.get("selected_sectors") or []
    dairy = aggregated.get("dairy") or {}

    legacy: dict[str, Any] = {
        "farm_name": farm.get("farm_name", "Farm"),
        "farm_type": "Mixed",
        "milking_cows": int(dairy.get("milking_cows") or 0),
        "litres_per_cow": float(dairy.get("litres_per_cow") or 0),
        "milk_price": float(dairy.get("milk_price") or 0),
        "other_revenue": float(aggregated.get("other_revenue") or 0),
        "opening_cash_balance": float(summary.get("opening_cash_balance") or 0),
        "biss": float(scheme.get("biss") or 0),
        "acres": float(scheme.get("acres") or 0),
        "scheme_payment_months": {
            "biss": scheme.get("scheme_payment_months", {}).get("biss", 10),
            "acres": scheme.get("scheme_payment_months", {}).get("acres", 12),
        },
        "feed": round(costs.get("feed", 0), 2),
        "fertiliser": round(costs.get("fertiliser", 0), 2),
        "vet": round(costs.get("vet", 0), 2),
        "contractor": round(costs.get("contractor", 0), 2),
        "labour": round(costs.get("labour", 0), 2),
        "insurance": round(costs.get("insurance", 0), 2),
        "loan_repayments": round(aggregated.get("loan_repayments_annual") or 0, 2),
        "fuel": round(costs.get("fuel", 0), 2),
        "electricity": round(costs.get("electricity", 0), 2),
        "_multi_sector": True,
        "_selected_sectors": selected,
        "_sector_metrics": {
            "beef": aggregated.get("beef"),
            "lamb": aggregated.get("lamb"),
            "dairy": aggregated.get("dairy"),
        },
        "monthly_forecast": _build_monthly_forecast(farm, aggregated),
        "kpi_visibility": get_kpi_visibility(selected),
    }
    for field in LEGACY_COST_FIELDS:
        legacy.setdefault(field, 0)
    return legacy


def load_farm_for_analysis(
    farm_file: str,
    sectors: list[str] | None = None,
) -> dict:
    raw = _read_farm_json(farm_file)
    if not is_multi_sector(raw):
        return raw
    selected = normalize_sectors(sectors, raw)
    filtered = filter_farm_by_sectors(raw, selected)
    aggregated = aggregate_sector_financials(filtered)
    return to_legacy_farm_dict(aggregated, raw)
