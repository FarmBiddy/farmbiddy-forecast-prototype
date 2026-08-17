"""
Manual financial-record persistence and aggregation (P0.2).

Farmer-entered income/expense records are stored per-farm under
`config.paths.FINANCIAL_RECORDS_DIR` - never inside `datasets/`, which is
the read-only, Git-committed canonical farm dataset. This keeps manual
entry from ever corrupting or reshaping that dataset.

Persistence is "write to a temp file, then atomically replace" so a crash
or concurrent request mid-write can never leave a half-written, corrupted
records file - the kind of safe/atomic persistence appropriate for this
prototype's single-process deployment. A process-local lock serialises
writes from concurrent requests within that one process; it does not
protect against multiple server processes writing the same file, which is
out of scope for this prototype.

Duplicate prevention (P1.2 boundary): once invoices/receipts can also
create `FinancialRecord`s, the same real-world transaction must not be
counted twice. Two mechanisms exist for that already:

  * `origin_document_id` is enforced unique - a given source document can
    only ever produce one financial record, no matter how many times an
    ingestion step runs.
  * `find_possible_duplicate` flags (but does not block) a new manual entry
    that looks identical to an existing one, so the caller/UI can warn the
    farmer rather than silently create a second copy of a genuine repeat
    transaction.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from config.paths import FINANCIAL_RECORDS_DIR
from models.financial_record import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    category_label,
    is_valid_category,
)

_LOCK = threading.Lock()


class DuplicateDocumentError(ValueError):
    """Raised when a document/import origin tries to create a second
    financial record for the same source document."""


class FinancialRecordNotFoundError(LookupError):
    pass


def _records_path(farm_file: str) -> str:
    stem = os.path.splitext(os.path.basename(farm_file))[0]
    os.makedirs(FINANCIAL_RECORDS_DIR, exist_ok=True)
    return os.path.join(FINANCIAL_RECORDS_DIR, f"{stem}.json")


def _load_records(farm_file: str) -> list[dict]:
    path = _records_path(farm_file)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _save_records(farm_file: str, records: list[dict]) -> None:
    path = _records_path(farm_file)
    directory = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_records_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_financial_records(
    farm_file: str,
    sectors: list[str] | None = None,
    record_type: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """All (non-deleted) records for a farm, newest first, optionally filtered."""
    records = _load_records(farm_file)
    if record_type:
        records = [r for r in records if r.get("record_type") == record_type]
    if category:
        records = [r for r in records if r.get("category") == category]
    if sectors:
        allowed = set(sectors)
        records = [r for r in records if not r.get("sector") or r.get("sector") in allowed]
    return sorted(records, key=lambda r: (r.get("date", ""), r.get("created_at", "")), reverse=True)


def get_financial_record(farm_file: str, record_id: str) -> dict:
    for record in _load_records(farm_file):
        if record.get("id") == record_id:
            return record
    raise FinancialRecordNotFoundError(record_id)


def find_possible_duplicate(farm_file: str, data: dict) -> dict | None:
    """A same-day, same-amount, same-category, same-type record already on file.

    This is a *hint*, not a hard block: farmers can legitimately have two
    identical transactions (e.g. two identical fuel top-ups the same day).
    Callers surface it as a warning so the farmer can decide.
    """
    for record in _load_records(farm_file):
        if (
            record.get("record_type") == data.get("record_type")
            and record.get("date") == data.get("date")
            and record.get("category") == data.get("category")
            and abs(float(record.get("amount") or 0) - float(data.get("amount") or 0)) < 0.005
        ):
            return record
    return None


def add_financial_record(
    farm_file: str,
    data: dict,
    origin: str = "manual",
    origin_document_id: str | None = None,
) -> tuple[dict, dict | None]:
    """Create and persist a new financial record.

    Returns (record, possible_duplicate) - the caller decides whether to
    surface the duplicate hint to the user; it never blocks creation for
    manual entries. For document/import origins, a duplicate
    `origin_document_id` *is* a hard error (see `DuplicateDocumentError`),
    since one source document must only ever produce one financial record.
    """
    with _LOCK:
        records = _load_records(farm_file)

        if origin_document_id:
            for record in records:
                if record.get("origin_document_id") == origin_document_id:
                    raise DuplicateDocumentError(
                        f"A financial record already exists for document '{origin_document_id}'.",
                    )

        possible_duplicate = find_possible_duplicate(farm_file, data)

        now = _now()
        record = {
            "id": uuid.uuid4().hex,
            "farm_file": farm_file,
            "record_type": data["record_type"],
            "date": data["date"],
            "category": data["category"],
            "amount": round(float(data["amount"]), 2),
            "description": data.get("description") or "",
            "counterparty": data.get("counterparty"),
            "notes": data.get("notes"),
            "sector": data.get("sector"),
            "origin": origin,
            "origin_document_id": origin_document_id,
            "created_at": now,
            "updated_at": now,
        }
        records.append(record)
        _save_records(farm_file, records)
        return record, possible_duplicate


def update_financial_record(farm_file: str, record_id: str, changes: dict) -> dict:
    """Edit the farmer-editable fields of an existing record.

    `record_type`, `origin`, and `origin_document_id` cannot be changed
    here (see `FinancialRecordUpdate`); a category change is still
    validated against the record's existing `record_type`.
    """
    with _LOCK:
        records = _load_records(farm_file)
        for record in records:
            if record.get("id") == record_id:
                if "category" in changes and changes["category"] is not None:
                    if not is_valid_category(record["record_type"], changes["category"]):
                        raise ValueError(f"Unknown {record['record_type']} category '{changes['category']}'.")
                for field in ("date", "category", "amount", "description", "counterparty", "notes", "sector"):
                    if field in changes and changes[field] is not None:
                        record[field] = round(float(changes[field]), 2) if field == "amount" else changes[field]
                record["updated_at"] = _now()
                _save_records(farm_file, records)
                return record
        raise FinancialRecordNotFoundError(record_id)


def delete_financial_record(farm_file: str, record_id: str) -> None:
    with _LOCK:
        records = _load_records(farm_file)
        remaining = [r for r in records if r.get("id") != record_id]
        if len(remaining) == len(records):
            raise FinancialRecordNotFoundError(record_id)
        _save_records(farm_file, remaining)


def aggregate_by_category(records: list[dict], record_type: str) -> list[dict]:
    """Category totals for one record type, highest first."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        if record.get("record_type") != record_type:
            continue
        cat = record.get("category") or "other"
        totals[cat] += float(record.get("amount") or 0)
        counts[cat] += 1
    rows = [
        {
            "category_id": cat,
            "label": category_label(record_type, cat),
            "total": round(total, 2),
            "count": counts[cat],
        }
        for cat, total in totals.items()
    ]
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


def manual_totals(records: list[dict]) -> tuple[float, float]:
    income = sum(float(r.get("amount") or 0) for r in records if r.get("record_type") == "income")
    expense = sum(float(r.get("amount") or 0) for r in records if r.get("record_type") == "expense")
    return round(income, 2), round(expense, 2)


def category_choices_payload() -> tuple[list[dict], list[dict]]:
    return list(INCOME_CATEGORIES), list(EXPENSE_CATEGORIES)
