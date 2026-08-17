"""
FinancialRecord storage: JSON-file and database implementations of the same
`load(farm_file) -> list[dict]` / `save(farm_file, records)` contract.

Business logic (dedup, validation, aggregation) lives entirely in
`services/financial_record_service.py`, unchanged by which of these is
active - see `config.settings.backend_for("FINANCIAL_RECORDS")`.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Protocol

from config.paths import FINANCIAL_RECORDS_DIR
from config.settings import backend_for

_LOCK = threading.Lock()


class FinancialRecordRepository(Protocol):
    def load(self, farm_file: str) -> list[dict]: ...
    def save(self, farm_file: str, records: list[dict]) -> None: ...


class JsonFinancialRecordRepository:
    """Direct continuation of the pre-P3 file-per-farm storage."""

    def _path(self, farm_file: str) -> str:
        stem = os.path.splitext(os.path.basename(farm_file))[0]
        os.makedirs(FINANCIAL_RECORDS_DIR, exist_ok=True)
        return os.path.join(FINANCIAL_RECORDS_DIR, f"{stem}.json")

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

    def save(self, farm_file: str, records: list[dict]) -> None:
        with _LOCK:
            path = self._path(farm_file)
            directory = os.path.dirname(path)
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp_records_", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(records, fh, indent=2)
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


class DbFinancialRecordRepository:
    """Database-backed storage, farm-scoped by a real foreign key.

    `save()` replaces the full set of a farm's records in one transaction
    (matching the JSON file's "whole file" semantics exactly, so the
    service layer's load-mutate-save business logic needs zero changes).
    This trades granular per-row CRUD efficiency for perfect behavioural
    parity with the pre-P3 storage during the P3 migration; moving to
    row-level create/update/delete statements is a reasonable future
    cleanup once DB parity has been running in production for a while.
    """

    def load(self, farm_file: str) -> list[dict]:
        from db.orm_models import FinancialRecord as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import format_date, format_datetime, to_float

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            rows = session.query(ORM).filter(ORM.farm_id == farm.id).all()
            return [
                {
                    "id": row.id,
                    "farm_file": farm_file,
                    "record_type": row.record_type,
                    "date": format_date(row.date),
                    "category": row.category,
                    "amount": to_float(row.amount),
                    "description": row.description or "",
                    "counterparty": row.counterparty,
                    "notes": row.notes,
                    "sector": row.sector,
                    "origin": row.origin,
                    "origin_document_id": row.origin_document_id,
                    "created_at": format_datetime(row.created_at),
                    "updated_at": format_datetime(row.updated_at),
                }
                for row in rows
            ]

    def save(self, farm_file: str, records: list[dict]) -> None:
        from db.orm_models import FinancialRecord as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import parse_date, parse_datetime

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            session.query(ORM).filter(ORM.farm_id == farm.id).delete()
            for record in records:
                session.add(ORM(
                    id=record["id"],
                    farm_id=farm.id,
                    record_type=record["record_type"],
                    date=parse_date(record["date"]),
                    category=record["category"],
                    amount=record["amount"],
                    description=record.get("description") or "",
                    counterparty=record.get("counterparty"),
                    notes=record.get("notes"),
                    sector=record.get("sector"),
                    origin=record.get("origin", "manual"),
                    origin_document_id=record.get("origin_document_id"),
                    created_at=parse_datetime(record.get("created_at")),
                    updated_at=parse_datetime(record.get("updated_at")),
                ))


def get_repository() -> FinancialRecordRepository:
    if backend_for("FINANCIAL_RECORDS") == "db":
        return DbFinancialRecordRepository()
    return JsonFinancialRecordRepository()
