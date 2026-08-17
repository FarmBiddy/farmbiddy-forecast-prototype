"""
Simple Farmer Onboarding persistence and effects (P1.3).

Storage mirrors the other farm_events stores: one JSON file per farm
under `config.paths.ONBOARDING_DIR`, written atomically. See
`models/onboarding.py` for the design decisions behind what onboarding
does and does not create.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timezone

from config.settings import backend_for
from models.financial_record import category_choices
from models.onboarding import FARM_TYPE_LABELS
from repositories.onboarding import get_repository
from services.category_budget_service import set_annual_budget

_LOCK = threading.Lock()

# Sectors the forecast engine actually models today. Farm types outside
# this map (Suckler, Tillage, Mixed, Other) are stored/labelled as given,
# never silently coerced onto a sector the engine cannot forecast.
FARM_TYPE_SECTOR_MAP: dict[str, list[str]] = {
    "dairy": ["dairy"],
    "beef": ["beef"],
    "sheep": ["lamb"],
}

LOAN_REPAYMENTS_CATEGORY = "loan_repayments"


def _load(farm_file: str) -> dict:
    return get_repository().load(farm_file)


def _save(farm_file: str, data: dict) -> None:
    get_repository().save(farm_file, data)


def _persist_farm_profile(farm_file: str, farm_type: str, sectors: list[str]) -> None:
    """P3.6: Simple Farm Setup also updates the farm's first-class `Farm`
    row (sectors, farm-type label) - not just the onboarding-overrides
    record - so a brand new farm created purely through onboarding (no
    pre-existing sample dataset) ends up with real, persisted farm
    configuration rather than only a read-time override. A no-op when the
    onboarding domain is still on the JSON backend (config/settings.py),
    since there is no Farm row concept there.
    """
    if backend_for("ONBOARDING") != "db":
        return
    from db.session import session_scope
    from identity.seed import get_or_create_farm

    with session_scope() as session:
        farm = get_or_create_farm(session, farm_file)
        if sectors:
            farm.sectors = sectors
        farm.settings = {**(farm.settings or {}), "farm_type": farm_type, "farm_type_label": FARM_TYPE_LABELS.get(farm_type, farm_type.title())}


def get_onboarding_overrides(farm_file: str) -> dict:
    """Raw stored onboarding record for a farm, or {} if never completed."""
    return _load(farm_file)


def get_current_cash_override(farm_file: str) -> float | None:
    value = get_onboarding_overrides(farm_file).get("current_cash")
    return float(value) if value is not None else None


def get_farm_type_override(farm_file: str) -> str | None:
    return get_onboarding_overrides(farm_file).get("farm_type")


def sectors_for_farm_type(farm_type: str | None) -> list[str] | None:
    """Best-effort mapping onto engine-modelled sectors, or None when this
    farm type has no equivalent (the caller should leave sectors as-is)."""
    if not farm_type:
        return None
    return FARM_TYPE_SECTOR_MAP.get(farm_type)


def get_onboarding_status(farm_file: str) -> dict:
    stored = get_onboarding_overrides(farm_file)
    farm_type = stored.get("farm_type")
    return {
        "success": True,
        "completed": bool(stored.get("completed_at")),
        "completed_at": stored.get("completed_at"),
        "farm_type": farm_type,
        "farm_type_label": FARM_TYPE_LABELS.get(farm_type) if farm_type else None,
        "current_cash": stored.get("current_cash"),
        "loan_repayments_annual": float(stored.get("loan_repayments_annual") or 0),
        "farm_types": [{"id": key, "label": label} for key, label in FARM_TYPE_LABELS.items()],
        "income_category_choices": category_choices("income"),
        "expense_category_choices": category_choices("expense"),
    }


def complete_onboarding(farm_file: str, data: dict) -> dict:
    """Apply a farmer's onboarding answers: set annual category budgets for
    main income/costs/loans, and store the farm_type/current_cash override.

    Returns an `OnboardingSummary`-shaped dict (see models/onboarding.py).
    """
    with _LOCK:
        year = data.get("year") or date.today().year
        farm_type = data["farm_type"]

        income_items = [i for i in data.get("income_items", []) if float(i.get("annual_amount") or 0) > 0]
        cost_items = [i for i in data.get("cost_items", []) if float(i.get("annual_amount") or 0) > 0]
        loan_items = data.get("loan_items") or []

        for item in income_items:
            set_annual_budget(farm_file, {
                "record_type": "income", "category": item["category"], "year": year,
                "annual_amount": float(item["annual_amount"]), "sector": None,
                "notes": "Set during Farm Setup",
            })

        # Loan repayments and any cost item the farmer separately entered for
        # the same category are combined into ONE annual figure so the second
        # write never silently discards the first (set_annual_budget is an
        # upsert on that category/year slot).
        loan_monthly_total = sum(float(li.get("monthly_repayment") or 0) for li in loan_items)
        loan_annual_total = round(loan_monthly_total * 12, 2)
        explicit_loan_cost_items = [c for c in cost_items if c["category"] == LOAN_REPAYMENTS_CATEGORY]
        other_cost_items = [c for c in cost_items if c["category"] != LOAN_REPAYMENTS_CATEGORY]
        combined_loan_annual = loan_annual_total + sum(float(c["annual_amount"]) for c in explicit_loan_cost_items)

        for item in other_cost_items:
            set_annual_budget(farm_file, {
                "record_type": "expense", "category": item["category"], "year": year,
                "annual_amount": float(item["annual_amount"]), "sector": None,
                "notes": "Set during Farm Setup",
            })
        if combined_loan_annual > 0:
            set_annual_budget(farm_file, {
                "record_type": "expense", "category": LOAN_REPAYMENTS_CATEGORY, "year": year,
                "annual_amount": combined_loan_annual, "sector": None,
                "notes": "Loan repayments estimated during Farm Setup",
            })

        current_cash = data.get("current_cash")
        stored = {
            "farm_type": farm_type,
            "current_cash": float(current_cash) if current_cash is not None else None,
            "loans": [dict(li) for li in loan_items],
            "loan_repayments_annual": combined_loan_annual,
            "year": year,
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save(farm_file, stored)
        _persist_farm_profile(farm_file, farm_type, sectors_for_farm_type(farm_type) or [])

        total_income = round(sum(float(i["annual_amount"]) for i in income_items), 2)
        total_cost = round(sum(float(c["annual_amount"]) for c in other_cost_items) + combined_loan_annual, 2)

        return {
            "farm_type": farm_type,
            "farm_type_label": FARM_TYPE_LABELS.get(farm_type, farm_type.title()),
            "selected_sectors": sectors_for_farm_type(farm_type) or [],
            "year": year,
            "income_budgets_set": len(income_items),
            "cost_budgets_set": len(other_cost_items) + (1 if combined_loan_annual > 0 else 0),
            "loan_repayments_annual": combined_loan_annual,
            "total_annual_income_budgeted": total_income,
            "total_annual_cost_budgeted": total_cost,
            "naive_annual_net": round(total_income - total_cost, 2),
            "current_cash_set": current_cash is not None,
            "current_cash": float(current_cash) if current_cash is not None else None,
        }
