"""Farmer-friendly category labels for upload preview and daily updates."""

from __future__ import annotations

FARMER_CATEGORIES: dict[str, str] = {
    "milk_income": "Milk income",
    "feed_costs": "Feed costs",
    "vet_costs": "Vet costs",
    "labour": "Labour",
    "machinery": "Machinery",
    "loans": "Loan payments",
    "fuel": "Fuel",
    "electricity": "Electricity",
    "fertiliser": "Fertiliser",
    "other_farm_expenses": "Other costs",
}

DAILY_UPDATE_CATEGORIES: dict[str, str] = {
    "milk_income": "Milk income",
    "feed_costs": "Feed purchases",
    "vet_costs": "Vet expenses",
    "fuel": "Fuel",
    "electricity": "Electricity",
    "labour": "Labour",
    "machinery": "Machinery",
    "fertiliser": "Fertiliser",
    "loans": "Loan payments",
    "other_farm_expenses": "Other costs",
}

DETECTED_FIELD_TO_CATEGORY: dict[str, str] = {
    "milk_revenue": "milk_income",
    "milk_litres": "milk_income",
    "grant_income": "milk_income",
    "other_income": "other_farm_expenses",
    "feed_cost": "feed_costs",
    "vet_cost": "vet_costs",
    "labour_cost": "labour",
    "machinery_cost": "machinery",
    "contractor_cost": "machinery",
    "loan_repayment": "loans",
    "fuel_cost": "fuel",
    "electricity_cost": "electricity",
    "fertiliser_cost": "fertiliser",
    "insurance_cost": "other_farm_expenses",
    "total_costs": "other_farm_expenses",
    "cash_balance": "other_farm_expenses",
    "profit": "other_farm_expenses",
}

CATEGORY_TO_PROFILE_FIELD: dict[str, str] = {
    "milk_income": "milk_price",
    "feed_costs": "feed",
    "vet_costs": "vet",
    "labour": "labour",
    "machinery": "contractor",
    "loans": "loan_repayments",
    "fuel": "fuel",
    "electricity": "electricity",
    "fertiliser": "fertiliser",
    "other_farm_expenses": "other_expenses",
}

DAILY_CATEGORY_TO_PROFILE_FIELD: dict[str, str] = {
    "milk_income": "opening_cash_balance",
    **{k: v for k, v in CATEGORY_TO_PROFILE_FIELD.items() if k != "milk_income"},
}
