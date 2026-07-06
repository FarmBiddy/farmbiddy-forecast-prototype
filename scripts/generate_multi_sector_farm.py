"""Generate datasets/multi_sector_farm.json with 24 months of realistic data."""

from __future__ import annotations

import json
import math
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
OUTPUT = os.path.join(BASE, "datasets", "multi_sector_farm.json")


def _season(month: int) -> float:
    """0-1 seasonal multiplier — spring peak for grass, winter trough."""
    return 0.85 + 0.15 * math.sin((month - 3) * math.pi / 6)


def _dairy_month(year: int, month: int) -> dict:
    cows = 96 if year == 2024 else 98
    litres_per_cow = 5200 / 12 * _season(month)
    milk_litres = round(cows * litres_per_cow, 0)
    milk_price = round(0.39 + 0.03 * math.sin(month / 12 * math.pi), 3)
    milk_rev = round(milk_litres * milk_price, 0)
    feed = round(7200 + 2800 * (1.1 - _season(month)), 0)
    costs = {
        "feed": feed,
        "concentrates": round(feed * 0.35, 0),
        "vet": round(900 + (400 if month in (2, 3) else 0), 0),
        "breeding": round(350 if month in (4, 5) else 120, 0),
        "labour": 4800,
        "machinery": 900,
        "fuel": round(650 + 200 * (1 - _season(month)), 0),
        "fertiliser": round(1100 if month in (3, 4, 8, 9) else 400, 0),
        "insurance": 420,
        "rent_land_lease": 0,
        "contractor": round(800 + 400 * (1 - _season(month)), 0),
        "animal_purchases": 0,
        "housing": 280,
        "equipment": 220,
    }
    costs["feed"] = feed + costs.pop("concentrates")
    total = sum(costs.values())
    costs["total"] = total
    return {
        "year": year,
        "month": month,
        "period": f"{year}-{month:02d}",
        "operational": {
            "milking_cows": cows,
            "milk_litres": milk_litres,
            "calves": 10 if month in (2, 3, 4) else 6,
            "dry_cows": 12,
        },
        "pricing": {"milk_price_per_litre": milk_price},
        "revenue": {"milk": milk_rev, "cattle_sales": 0, "lamb_sales": 0, "wool": 0, "other": 0, "total": milk_rev},
        "costs": costs,
        "notes": "Higher concentrate use in winter" if month <= 2 or month >= 11 else "",
    }


def _beef_month(year: int, month: int) -> dict:
    cattle = 52 if month <= 6 else 48
    sold = 4 if month in (6, 9, 11) else (2 if month in (3, 7) else 0)
    price = round(1320 + 180 * math.sin((month - 1) * math.pi / 6), 0)
    purchases = round(5200 if month in (1, 4, 10) else 0, 0)
    sales_rev = round(sold * price, 0)
    feed = round(4200 + 1500 * (1.1 - _season(month)), 0)
    costs = {
        "feed": feed,
        "vet": round(450 + (200 if month in (1, 2) else 0), 0),
        "breeding": 80,
        "labour": 2200,
        "machinery": 500,
        "fuel": 380,
        "fertiliser": 300,
        "insurance": 180,
        "rent_land_lease": 0,
        "contractor": 420,
        "animal_purchases": purchases,
        "housing": 350,
        "equipment": 150,
    }
    total = sum(costs.values())
    costs["total"] = total
    rev_total = sales_rev
    return {
        "year": year,
        "month": month,
        "period": f"{year}-{month:02d}",
        "operational": {
            "cattle_on_farm": cattle,
            "cattle_purchased": 3 if purchases else 0,
            "cattle_sold": sold,
            "finishing_units": 28,
        },
        "pricing": {"beef_sale_price_per_head": price},
        "revenue": {
            "milk": 0,
            "cattle_sales": sales_rev,
            "lamb_sales": 0,
            "wool": 0,
            "other": 0,
            "total": rev_total,
        },
        "costs": costs,
        "notes": "Store cattle sales in autumn" if month in (9, 11) else "",
    }


def _lamb_month(year: int, month: int) -> dict:
    ewes = 228
    lambs_born = 180 if month == 3 else (90 if month == 4 else 0)
    lambs_sold = 45 if month in (7, 8, 9) else (25 if month == 10 else 0)
    lamb_kg = 42
    lamb_price = round(6.4 + 0.8 * math.sin((month - 6) * math.pi / 6), 2)
    wool = 850 if month == 6 else 0
    lamb_rev = round(lambs_sold * lamb_kg * lamb_price, 0) if lambs_sold else 0
    feed = round(2800 + (4200 if month in (3, 4) else 1800 * (1.1 - _season(month))), 0)
    vet = round(600 + (2400 if month in (3, 4) else 0), 0)
    costs = {
        "feed": feed,
        "vet": vet,
        "breeding": round(200 if month in (10, 11) else 50, 0),
        "labour": 1800,
        "machinery": 320,
        "fuel": 280,
        "fertiliser": 250,
        "insurance": 140,
        "rent_land_lease": 0,
        "contractor": 280,
        "animal_purchases": 0,
        "housing": 200,
        "equipment": 90,
    }
    total = sum(costs.values())
    costs["total"] = total
    rev_total = lamb_rev + wool
    note = "Peak lambing — elevated vet and feed" if month in (3, 4) else ""
    if month in (7, 8) and lambs_sold:
        note = "Main lamb sales window"
    return {
        "year": year,
        "month": month,
        "period": f"{year}-{month:02d}",
        "operational": {
            "ewes": ewes,
            "lambs_born": lambs_born,
            "lambs_sold": lambs_sold,
            "rams": 6,
            "mortality_notes": "Minor ewe losses at lambing" if month == 3 else None,
        },
        "pricing": {"lamb_price_per_kg": lamb_price, "wool_income": wool},
        "revenue": {
            "milk": 0,
            "cattle_sales": 0,
            "lamb_sales": lamb_rev,
            "wool": wool,
            "other": 0,
            "total": rev_total,
        },
        "costs": costs,
        "notes": note,
    }


def build_dataset() -> dict:
    monthly_dairy, monthly_beef, monthly_lamb = [], [], []
    for year in (2024, 2025):
        for month in range(1, 13):
            monthly_dairy.append(_dairy_month(year, month))
            monthly_beef.append(_beef_month(year, month))
            monthly_lamb.append(_lamb_month(year, month))

    return {
        "schema_version": "2.0",
        "farm_name": "Knockrow Mixed Farm",
        "identity": {
            "legal_entity": {
                "name": "Knockrow Mixed Farm Ltd",
                "type": "Private Company Limited by Shares",
                "registration_number": "IE-4829173",
                "vat_number": "IE9847291K",
            },
            "farmer": {
                "name": "Patrick O'Sullivan",
                "client_id": "FB-CL-10482",
                "phone": "+353 87 123 4567",
                "email": "patrick.osullivan@knockrowfarm.ie",
                "address": "Knockrow, Cahir, Co. Tipperary, E21 XY12",
            },
            "location": {
                "county": "Tipperary",
                "country": "Ireland",
                "herd_number": "IE-3728491",
                "coordinates": {"lat": 52.376, "lng": -7.921},
            },
        },
        "farm_summary": {
            "total_hectares": 185,
            "opening_cash_balance": 28500,
            "debtors": 14200,
            "creditors": 19600,
            "loans": [
                {
                    "lender": "AIB Agri Finance",
                    "principal": 185000,
                    "monthly_repayment": 2100,
                    "rate": 4.85,
                    "maturity": "2031-06",
                },
                {
                    "lender": "Credit Union Cahir",
                    "principal": 35000,
                    "monthly_repayment": 680,
                    "rate": 5.2,
                    "maturity": "2028-03",
                },
            ],
            "supplier_credit": [
                {"supplier": "Dairygold Co-op", "balance": 8400, "terms_days": 30},
                {"supplier": "Tipperary Co-op Store", "balance": 3200, "terms_days": 45},
            ],
            "notes": "Mixed enterprise — dairy, beef finishing, and sheep. Family labour with one part-time employee.",
        },
        "scheme_payments": {
            "biss": 22400,
            "acres": 9200,
            "other_grants": 3500,
            "scheme_payment_months": {"biss": 10, "acres": 12, "other_grants": 11},
        },
        "available_sectors": ["dairy", "beef", "lamb"],
        "sectors": {
            "dairy": {
                "display_name": "Dairy",
                "processor": "Lakeland Dairies",
                "herd": {
                    "milking_cows": 98,
                    "dry_cows": 12,
                    "calves": 8,
                    "replacement_heifers": 24,
                },
                "monthly": monthly_dairy,
            },
            "beef": {
                "display_name": "Beef",
                "herd": {"cattle_on_farm": 50, "finishing_units": 28},
                "monthly": monthly_beef,
            },
            "lamb": {
                "display_name": "Lamb / Sheep",
                "flock": {"ewes": 228, "lambs": 180, "rams": 6},
                "monthly": monthly_lamb,
            },
        },
        "metadata": {
            "currency": "EUR",
            "data_period": {"start": "2024-01", "end": "2025-12", "months": 24},
            "seasonal_notes": [
                {"period": "2024-03", "sector": "lamb", "note": "Peak lambing — elevated vet and feed costs"},
                {"period": "2024-07", "sector": "lamb", "note": "Main lamb sales window"},
                {"period": "2024-11", "sector": "beef", "note": "Autumn store cattle sales"},
                {"period": "2025-01", "sector": "dairy", "note": "Winter milk — higher concentrate feeding"},
            ],
        },
    }


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(build_dataset(), fh, indent=2)
    print(f"Wrote {OUTPUT}")
