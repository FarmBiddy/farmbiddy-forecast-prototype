"""
P3.7 - Farm-level data export/restore.

A whole-database backup (see `scripts/backup_database.py`) protects against
losing everything. This module protects a single farm's data at a finer
grain, and doubles as the "documented path to recovering financial records
if persistence fails" the P3 brief requires: export a farm to one portable
JSON file today, restore it (into the same or a fresh database) tomorrow.

It reads/writes through the exact same repository interfaces the services
use (`repositories/*.get_repository()`), so:
  * the export format is backend-agnostic - it works whether a domain is
    currently on "json" or "db", and restoring writes through whichever
    backend is active at restore time;
  * it can never drift out of sync with what the app actually persists,
    because it is not a second, parallel serialisation of the domain
    models - it *is* the domain models' own load()/save() contract.

Usage:
    python -m scripts.farm_data_export export <farm_file> [--output PATH]
    python -m scripts.farm_data_export restore <export_file> [--farm-file FARM_FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from config.paths import STORAGE_ROOT
from config.settings import backend_for

DEFAULT_EXPORT_DIR = os.path.join(STORAGE_ROOT, "backups", "farm_exports")

EXPORT_FORMAT_VERSION = 1


def _farm_profile(farm_file: str) -> dict | None:
    """Best-effort read of the farm's first-class profile row. Returns
    `None` rather than raising if the DB isn't reachable for some reason -
    a farm-data export should never fail just because the optional profile
    metadata couldn't be read."""
    try:
        from db.session import session_scope
        from identity.seed import get_or_create_farm

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            return {
                "slug": farm.slug,
                "name": farm.name,
                "sectors": list(farm.sectors or []),
                "settings": dict(farm.settings or {}),
                "dataset_file": farm.dataset_file,
            }
    except Exception:
        return None


def export_farm(farm_file: str) -> dict:
    """Build a full, portable snapshot of one farm's owned data."""
    import repositories.category_budgets as category_budgets_repo
    import repositories.documents as documents_repo
    import repositories.financial_records as financial_records_repo
    import repositories.loans as loans_repo
    import repositories.onboarding as onboarding_repo

    return {
        "export_format_version": EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "farm_file": farm_file,
        "farm_profile": _farm_profile(farm_file),
        "financial_records": financial_records_repo.get_repository().load(farm_file),
        "documents": documents_repo.get_repository().load(farm_file),
        "category_budgets": category_budgets_repo.get_repository().load(farm_file),
        "loans": loans_repo.get_repository().load(farm_file),
        "onboarding": onboarding_repo.get_repository().load(farm_file),
    }


def write_export(farm_file: str, output_path: str | None = None) -> str:
    data = export_farm(farm_file)
    if output_path is None:
        os.makedirs(DEFAULT_EXPORT_DIR, exist_ok=True)
        stem = os.path.splitext(os.path.basename(farm_file))[0]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = os.path.join(DEFAULT_EXPORT_DIR, f"{stem}_{timestamp}.json")
    else:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return output_path


def _remap_ids(records: list[dict], id_map: dict[str, str]) -> list[dict]:
    remapped = []
    for record in records:
        new_record = dict(record)
        old_id = new_record.get("id")
        if old_id:
            new_record["id"] = id_map.setdefault(old_id, uuid.uuid4().hex)
        remapped.append(new_record)
    return remapped


def restore_farm(export_data: dict, farm_file: str | None = None) -> dict:
    """Replay an export back through the live repository layer. Returns a
    summary of what was restored, e.g. for a post-restore sanity check.

    Record/document ids are preserved as-is when restoring into the *same*
    farm the export came from (the disaster-recovery case: `save()` clears
    that farm's existing rows first, so there is nothing to collide with).
    Restoring into a *different* farm_file (e.g. cloning a farm's data)
    regenerates every id - and remaps the financial-record<->document
    cross-references that travel with them - since `id` is a
    globally-unique primary key shared by every farm's rows, not scoped
    per farm.

    `loans` is only restored when the export actually captured DB-backed
    loan rows (`loans` is not `None` - see `repositories/loans.py`'s "no
    rows recorded" sentinel) *and* the loans domain is currently DB-backed;
    otherwise a farm still on the dataset-embedded loans is left untouched
    rather than raising `NotImplementedError` from `JsonLoanRepository`.
    """
    import repositories.category_budgets as category_budgets_repo
    import repositories.documents as documents_repo
    import repositories.financial_records as financial_records_repo
    import repositories.loans as loans_repo
    import repositories.onboarding as onboarding_repo

    original_farm_file = export_data["farm_file"]
    farm_file = farm_file or original_farm_file
    same_farm = farm_file == original_farm_file
    summary: dict = {"farm_file": farm_file}

    financial_records = list(export_data.get("financial_records") or [])
    documents = list(export_data.get("documents") or [])
    category_budgets = list(export_data.get("category_budgets") or [])

    if not same_farm:
        record_id_map: dict[str, str] = {}
        doc_id_map: dict[str, str] = {}
        financial_records = _remap_ids(financial_records, record_id_map)
        documents = _remap_ids(documents, doc_id_map)
        category_budgets = _remap_ids(category_budgets, {})
        for record in financial_records:
            if record.get("origin_document_id") in doc_id_map:
                record["origin_document_id"] = doc_id_map[record["origin_document_id"]]
        for document in documents:
            if document.get("linked_financial_record_id") in record_id_map:
                document["linked_financial_record_id"] = record_id_map[document["linked_financial_record_id"]]
            if document.get("possible_duplicate_manual_record_id") in record_id_map:
                document["possible_duplicate_manual_record_id"] = record_id_map[
                    document["possible_duplicate_manual_record_id"]
                ]

    financial_records_repo.get_repository().save(farm_file, financial_records)
    summary["financial_records"] = len(financial_records)

    documents_repo.get_repository().save(farm_file, documents)
    summary["documents"] = len(documents)

    category_budgets_repo.get_repository().save(farm_file, category_budgets)
    summary["category_budgets"] = len(category_budgets)

    onboarding_repo.get_repository().save(farm_file, export_data.get("onboarding") or {})
    summary["onboarding_restored"] = bool(export_data.get("onboarding"))

    exported_loans = export_data.get("loans")
    if exported_loans is not None and backend_for("LOANS") == "db":
        loans_repo.get_repository().save(farm_file, exported_loans)
        summary["loans"] = len(exported_loans)
    else:
        summary["loans"] = "skipped (no DB loan rows in export, or loans domain not DB-backed)"

    farm_profile = export_data.get("farm_profile")
    if farm_profile and any(backend_for(domain) == "db" for domain in (
        "FINANCIAL_RECORDS", "DOCUMENTS", "CATEGORY_BUDGETS", "ONBOARDING", "LOANS",
    )):
        from db.session import session_scope
        from identity.seed import get_or_create_farm

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            farm.name = farm_profile.get("name", farm.name)
            farm.sectors = farm_profile.get("sectors", farm.sectors)
            farm.settings = farm_profile.get("settings", farm.settings)
        summary["farm_profile_restored"] = True
    else:
        summary["farm_profile_restored"] = False

    return summary


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export one farm's data to a JSON file")
    export_parser.add_argument("farm_file")
    export_parser.add_argument("--output", default=None)

    restore_parser = subparsers.add_parser("restore", help="Restore a farm from a previously exported JSON file")
    restore_parser.add_argument("export_file")
    restore_parser.add_argument("--farm-file", default=None)

    args = parser.parse_args(argv)

    if args.command == "export":
        path = write_export(args.farm_file, args.output)
        print(f"Farm export written to: {path}")
    elif args.command == "restore":
        with open(args.export_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        summary = restore_farm(data, args.farm_file)
        print(f"Restore summary: {json.dumps(summary, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
