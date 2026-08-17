"""Onboarding profile storage - one dict per farm (not a list), otherwise the
same JSON/DB dual-path design as the other domains."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Protocol

from config.paths import ONBOARDING_DIR
from config.settings import backend_for

_LOCK = threading.Lock()


class OnboardingRepository(Protocol):
    def load(self, farm_file: str) -> dict: ...
    def save(self, farm_file: str, data: dict) -> None: ...


class JsonOnboardingRepository:
    def _path(self, farm_file: str) -> str:
        stem = os.path.splitext(os.path.basename(farm_file))[0]
        os.makedirs(ONBOARDING_DIR, exist_ok=True)
        return os.path.join(ONBOARDING_DIR, f"{stem}.json")

    def load(self, farm_file: str) -> dict:
        path = self._path(farm_file)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                return {}
        return data if isinstance(data, dict) else {}

    def save(self, farm_file: str, data: dict) -> None:
        with _LOCK:
            path = self._path(farm_file)
            directory = os.path.dirname(path)
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp_onboarding_", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


class DbOnboardingRepository:
    def load(self, farm_file: str) -> dict:
        from db.orm_models import OnboardingProfile as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import format_datetime, to_float

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            row = session.get(ORM, farm.id)
            if row is None or not row.completed_at:
                return {}
            return {
                "farm_type": row.farm_type,
                "current_cash": to_float(row.current_cash) if row.current_cash is not None else None,
                "loans": list(row.loans or []),
                "loan_repayments_annual": to_float(row.loan_repayments_annual),
                "year": row.year,
                "completed_at": format_datetime(row.completed_at),
            }

    def save(self, farm_file: str, data: dict) -> None:
        from db.orm_models import OnboardingProfile as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import parse_datetime

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            row = session.get(ORM, farm.id)
            if row is None:
                row = ORM(farm_id=farm.id)
                session.add(row)
            row.farm_type = data.get("farm_type")
            row.current_cash = data.get("current_cash")
            row.loans = data.get("loans") or []
            row.loan_repayments_annual = data.get("loan_repayments_annual") or 0
            row.year = data.get("year")
            row.completed_at = parse_datetime(data.get("completed_at"))


def get_repository() -> OnboardingRepository:
    if backend_for("ONBOARDING") == "db":
        return DbOnboardingRepository()
    return JsonOnboardingRepository()
