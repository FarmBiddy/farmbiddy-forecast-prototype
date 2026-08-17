"""
Category-level budget persistence and CRUD (P0.3).

Storage follows the same safe/atomic pattern as
`services/financial_record_service.py`: one JSON file per farm under
`config.paths.CATEGORY_BUDGETS_DIR`, written via temp-file + atomic
replace, serialised by a process-local lock. This is a distinct file from
financial records and from the read-only dataset, so a budget (a plan) can
never be confused with, or accidentally merged into, an Actual.

Setting a budget for a given (sector, record_type, category, year, month)
is an upsert: calling it twice for the same slot replaces the figure
rather than accumulating duplicate rows, matching the farmer's mental
model of "the Feed budget for March is now EUR450", not "add another Feed
budget for March".
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone

from config.paths import CATEGORY_BUDGETS_DIR
from models.financial_record import is_valid_category

_LOCK = threading.Lock()


class CategoryBudgetNotFoundError(LookupError):
    pass


def _budgets_path(farm_file: str) -> str:
    stem = os.path.splitext(os.path.basename(farm_file))[0]
    os.makedirs(CATEGORY_BUDGETS_DIR, exist_ok=True)
    return os.path.join(CATEGORY_BUDGETS_DIR, f"{stem}.json")


def _load_budgets(farm_file: str) -> list[dict]:
    path = _budgets_path(farm_file)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _save_budgets(farm_file: str, budgets: list[dict]) -> None:
    path = _budgets_path(farm_file)
    directory = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_budgets_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(budgets, fh, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_category_budgets(
    farm_file: str,
    sectors: list[str] | None = None,
    record_type: str | None = None,
    category: str | None = None,
    year: int | None = None,
) -> list[dict]:
    """All budget records for a farm, optionally filtered. Newest-set first."""
    budgets = _load_budgets(farm_file)
    if record_type:
        budgets = [b for b in budgets if b.get("record_type") == record_type]
    if category:
        budgets = [b for b in budgets if b.get("category") == category]
    if year is not None:
        budgets = [b for b in budgets if b.get("year") == year]
    if sectors:
        allowed = set(sectors)
        budgets = [b for b in budgets if not b.get("sector") or b.get("sector") in allowed]
    return sorted(budgets, key=lambda b: (b.get("year", 0), b.get("month", 0), b.get("category", "")))


def get_category_budget(farm_file: str, budget_id: str) -> dict:
    for budget in _load_budgets(farm_file):
        if budget.get("id") == budget_id:
            return budget
    raise CategoryBudgetNotFoundError(budget_id)


def _upsert(
    records: list[dict],
    farm_file: str,
    sector: str | None,
    record_type: str,
    category: str,
    year: int,
    month: int,
    amount: float,
    source: str,
    annual_total: float | None,
    allocation_rule: str | None,
    notes: str | None,
) -> dict:
    now = _now()
    for record in records:
        if (
            record.get("sector") == sector
            and record.get("record_type") == record_type
            and record.get("category") == category
            and record.get("year") == year
            and record.get("month") == month
        ):
            record.update({
                "amount": round(float(amount), 2),
                "source": source,
                "annual_total": round(float(annual_total), 2) if annual_total is not None else None,
                "allocation_rule": allocation_rule,
                "notes": notes if notes is not None else record.get("notes"),
                "updated_at": now,
            })
            return record

    record = {
        "id": uuid.uuid4().hex,
        "farm_file": farm_file,
        "sector": sector,
        "record_type": record_type,
        "category": category,
        "year": year,
        "month": month,
        "amount": round(float(amount), 2),
        "source": source,
        "annual_total": round(float(annual_total), 2) if annual_total is not None else None,
        "allocation_rule": allocation_rule,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    }
    records.append(record)
    return record


def set_monthly_budget(farm_file: str, data: dict) -> dict:
    """Create or replace the budget for one category in one specific month."""
    record_type = data["record_type"]
    category = data["category"]
    if not is_valid_category(record_type, category):
        raise ValueError(f"Unknown {record_type} category '{category}'.")
    with _LOCK:
        records = _load_budgets(farm_file)
        result = _upsert(
            records, farm_file,
            sector=data.get("sector"),
            record_type=record_type,
            category=category,
            year=int(data["year"]),
            month=int(data["month"]),
            amount=data["amount"],
            source="monthly",
            annual_total=None,
            allocation_rule=None,
            notes=data.get("notes"),
        )
        _save_budgets(farm_file, records)
        return result


def set_annual_budget(farm_file: str, data: dict) -> list[dict]:
    """Split one annual figure evenly across the 12 calendar months of `year`.

    The last month absorbs the rounding remainder so the 12 parts always
    sum exactly to the annual figure the farmer typed in - never a
    fabricated approximation drifting away from what they entered.
    """
    record_type = data["record_type"]
    category = data["category"]
    if not is_valid_category(record_type, category):
        raise ValueError(f"Unknown {record_type} category '{category}'.")
    annual_amount = round(float(data["annual_amount"]), 2)
    year = int(data["year"])
    base = round(annual_amount / 12, 2)
    monthly_amounts = [base] * 11
    monthly_amounts.append(round(annual_amount - base * 11, 2))

    with _LOCK:
        records = _load_budgets(farm_file)
        created: list[dict] = []
        for month, amount in enumerate(monthly_amounts, start=1):
            created.append(_upsert(
                records, farm_file,
                sector=data.get("sector"),
                record_type=record_type,
                category=category,
                year=year,
                month=month,
                amount=amount,
                source="annual_allocation",
                annual_total=annual_amount,
                allocation_rule="even_12",
                notes=data.get("notes"),
            ))
        _save_budgets(farm_file, records)
        return created


def update_category_budget(farm_file: str, budget_id: str, changes: dict) -> dict:
    with _LOCK:
        records = _load_budgets(farm_file)
        for record in records:
            if record.get("id") == budget_id:
                if changes.get("amount") is not None:
                    record["amount"] = round(float(changes["amount"]), 2)
                if changes.get("notes") is not None:
                    record["notes"] = changes["notes"]
                record["updated_at"] = _now()
                _save_budgets(farm_file, records)
                return record
        raise CategoryBudgetNotFoundError(budget_id)


def delete_category_budget(farm_file: str, budget_id: str) -> None:
    with _LOCK:
        records = _load_budgets(farm_file)
        remaining = [r for r in records if r.get("id") != budget_id]
        if len(remaining) == len(records):
            raise CategoryBudgetNotFoundError(budget_id)
        _save_budgets(farm_file, remaining)


def budget_lookup(
    farm_file: str,
    sectors: list[str] | None = None,
) -> dict[tuple, dict]:
    """(record_type, category, year, month) -> resolved budget record.

    When both a sector-specific and a whole-farm (sector=None) budget
    exist for the same slot, the sector-specific one wins - it is the more
    precise figure the farmer set. This never sums the two, which would
    double count.
    """
    budgets = list_category_budgets(farm_file, sectors=sectors)
    resolved: dict[tuple, dict] = {}
    for budget in budgets:
        key = (budget["record_type"], budget["category"], budget["year"], budget["month"])
        existing = resolved.get(key)
        if existing is None or (existing.get("sector") is None and budget.get("sector") is not None):
            resolved[key] = budget
    return resolved
