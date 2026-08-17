"""Document (invoice/receipt) storage - see `repositories/financial_records.py`
for the shared design notes (this mirrors it exactly)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Protocol

from config.paths import DOCUMENTS_DIR
from config.settings import backend_for

_LOCK = threading.Lock()


class DocumentRepository(Protocol):
    def load(self, farm_file: str) -> list[dict]: ...
    def save(self, farm_file: str, documents: list[dict]) -> None: ...


class JsonDocumentRepository:
    def _path(self, farm_file: str) -> str:
        stem = os.path.splitext(os.path.basename(farm_file))[0]
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        return os.path.join(DOCUMENTS_DIR, f"{stem}.json")

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

    def save(self, farm_file: str, documents: list[dict]) -> None:
        with _LOCK:
            path = self._path(farm_file)
            directory = os.path.dirname(path)
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp_documents_", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(documents, fh, indent=2)
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


class DbDocumentRepository:
    def load(self, farm_file: str) -> list[dict]:
        from db.orm_models import Document as ORM
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
                    "document_type": row.document_type,
                    "record_type": row.record_type,
                    "date": format_date(row.date),
                    "counterparty": row.counterparty,
                    "amount": to_float(row.amount),
                    "category": row.category,
                    "payment_status": row.payment_status,
                    "payment_date": format_date(row.payment_date),
                    "reference": row.reference,
                    "attachment_reference": row.attachment_reference,
                    "notes": row.notes,
                    "sector": row.sector,
                    "source": row.source,
                    "provider_reference": row.provider_reference,
                    "extraction_confidence": row.extraction_confidence,
                    "review_status": row.review_status,
                    "linked_financial_record_id": row.linked_financial_record_id,
                    "possible_duplicate_manual_record_id": row.possible_duplicate_manual_record_id,
                    "created_at": format_datetime(row.created_at),
                    "updated_at": format_datetime(row.updated_at),
                }
                for row in rows
            ]

    def save(self, farm_file: str, documents: list[dict]) -> None:
        from db.orm_models import Document as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import parse_date, parse_datetime

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            session.query(ORM).filter(ORM.farm_id == farm.id).delete()
            for document in documents:
                session.add(ORM(
                    id=document["id"],
                    farm_id=farm.id,
                    document_type=document["document_type"],
                    record_type=document["record_type"],
                    date=parse_date(document["date"]),
                    counterparty=document["counterparty"],
                    amount=document["amount"],
                    category=document["category"],
                    payment_status=document["payment_status"],
                    payment_date=parse_date(document.get("payment_date")),
                    reference=document.get("reference"),
                    attachment_reference=document.get("attachment_reference"),
                    notes=document.get("notes"),
                    sector=document.get("sector"),
                    source=document.get("source", "manual"),
                    provider_reference=document.get("provider_reference"),
                    extraction_confidence=document.get("extraction_confidence"),
                    review_status=document.get("review_status", "confirmed"),
                    linked_financial_record_id=document.get("linked_financial_record_id"),
                    possible_duplicate_manual_record_id=document.get("possible_duplicate_manual_record_id"),
                    created_at=parse_datetime(document.get("created_at")),
                    updated_at=parse_datetime(document.get("updated_at")),
                ))


def get_repository() -> DocumentRepository:
    if backend_for("DOCUMENTS") == "db":
        return DbDocumentRepository()
    return JsonDocumentRepository()
