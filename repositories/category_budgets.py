"""Category budget storage - see `repositories/financial_records.py` for the
shared design notes (this mirrors it exactly)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Protocol

from config.paths import CATEGORY_BUDGETS_DIR
from config.settings import backend_for

_LOCK = threading.Lock()


class CategoryBudgetRepository(Protocol):
    def load(self, farm_file: str) -> list[dict]: ...
    def save(self, farm_file: str, budgets: list[dict]) -> None: ...


class JsonCategoryBudgetRepository:
    def _path(self, farm_file: str) -> str:
        stem = os.path.splitext(os.path.basename(farm_file))[0]
        os.makedirs(CATEGORY_BUDGETS_DIR, exist_ok=True)
        return os.path.join(CATEGORY_BUDGETS_DIR, f"{stem}.json")

    def load(self, farm_file: str) -> list[dict]:
        path = self._path(farm_file)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                return []
        return data if isinstance(data, list) else []

    def save(self, farm_file: str, budgets: list[dict]) -> None:
        with _LOCK:
            path = self._path(farm_file)
            directory = os.path.dirname(path)
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp_budgets_", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(budgets, fh, indent=2)
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


class DbCategoryBudgetRepository:
    def load(self, farm_file: str) -> list[dict]:
        from db.orm_models import CategoryBudget as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import format_datetime, to_float

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            rows = session.query(ORM).filter(ORM.farm_id == farm.id).all()
            return [
                {
                    "id": row.id,
                    "farm_file": farm_file,
                    "sector": row.sector,
                    "record_type": row.record_type,
                    "category": row.category,
                    "year": row.year,
                    "month": row.month,
                    "amount": to_float(row.amount),
                    "source": row.source,
                    "annual_total": to_float(row.annual_total) if row.annual_total is not None else None,
                    "allocation_rule": row.allocation_rule,
                    "notes": row.notes,
                    "created_at": format_datetime(row.created_at),
                    "updated_at": format_datetime(row.updated_at),
                }
                for row in rows
            ]

    def save(self, farm_file: str, budgets: list[dict]) -> None:
        from db.orm_models import CategoryBudget as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import parse_datetime

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            session.query(ORM).filter(ORM.farm_id == farm.id).delete()
            for budget in budgets:
                session.add(ORM(
                    id=budget["id"],
                    farm_id=farm.id,
                    sector=budget.get("sector"),
                    record_type=budget["record_type"],
                    category=budget["category"],
                    year=budget["year"],
                    month=budget["month"],
                    amount=budget["amount"],
                    source=budget.get("source", "monthly"),
                    annual_total=budget.get("annual_total"),
                    allocation_rule=budget.get("allocation_rule"),
                    notes=budget.get("notes"),
                    created_at=parse_datetime(budget.get("created_at")),
                    updated_at=parse_datetime(budget.get("updated_at")),
                ))


def get_repository() -> CategoryBudgetRepository:
    if backend_for("CATEGORY_BUDGETS") == "db":
        return DbCategoryBudgetRepository()
    return JsonCategoryBudgetRepository()
