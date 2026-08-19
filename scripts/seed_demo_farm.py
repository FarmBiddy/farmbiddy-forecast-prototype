"""
P4.6 - Seed the canonical demo farm with farmer-owned records that go
through the same services a real farm would use.

Does NOT import dataset historical actuals as FinancialRecords (that would
double-count against `dataset_coverage_cutoff`). Only writes:

* FinancialRecords dated after the dataset's last covered month
* Documents (one paid receipt, one unpaid invoice)
* Category budgets that create a visible ahead/behind variance

Idempotent: records/documents/budgets tagged with DEMO_MARKER are skipped
if already present.

Usage:
    python -m scripts.seed_demo_farm
    python -m scripts.seed_demo_farm --farm-file multi_sector_farm.json
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEMO_MARKER = "[DEMO]"
DEFAULT_FARM = "multi_sector_farm.json"


def _cutoff_year_month(farm_file: str) -> tuple[int, int]:
    from services.dashboard_summary import dataset_coverage_cutoff
    from services.multi_sector_farm import load_multi_sector_farm

    cutoff = dataset_coverage_cutoff(load_multi_sector_farm(farm_file))
    if cutoff:
        return cutoff
    return (2025, 8)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _has_record(records: list[dict], marker: str) -> bool:
    """Check if a record with a specific marker string already exists."""
    return any(marker in (r.get("description") or "") for r in records)


def _has_document(documents: list[dict], marker: str) -> bool:
    """Check if a document with a specific marker string already exists."""
    return any(marker in (d.get("notes") or "") for d in documents)


# ── Document definitions ────────────────────────────────────────────
# Each tuple: (document_type, record_type, counterparty, amount, category, payment_status, notes_suffix)
HOUSEHOLD_DOCUMENTS: list[tuple[str, str, str, float, str, str, str]] = [
    ("receipt", "expense", "Electric Ireland", 285.0, "utilities",
     "paid", "Household electricity Q1"),
    ("receipt", "expense", "Dunnes Stores", 165.0, "other_expense",
     "paid", "Household supplies"),
    ("invoice", "expense", "Bord Gáis Energy", 310.0, "utilities",
     "unpaid", "Household gas bill"),
    ("invoice", "expense", "Home Maintenance Co", 420.0, "other_expense",
     "unpaid", "Household plumbing repair"),
]


def seed_demo_farm(farm_file: str = DEFAULT_FARM) -> dict:
    """Write demo farmer-owned data through live services. Safe to re-run."""
    from config.settings import IS_SQLITE
    from db.session import init_db
    from services.category_budget_service import list_category_budgets, set_monthly_budget
    from services.document_service import add_document, list_documents
    from services.financial_record_service import add_financial_record, list_financial_records

    if IS_SQLITE:
        init_db()

    year, month = _next_month(*_cutoff_year_month(farm_file))
    date = f"{year:04d}-{month:02d}-12"

    created: dict[str, int] = {"records": 0, "documents": 0, "budgets": 0}

    # ── Financial records (base demo data) ──────────────────────────
    existing_records = list_financial_records(farm_file)
    base_records = [
        ("income", "milk", 18500.0, "Milk cheque", "Lakeland Dairies"),
        ("income", "livestock", 4200.0, "Finished cattle sale", "Mart"),
        ("expense", "feed", 6200.0, "Ration delivery", "Co-op Store"),
        ("expense", "fertiliser", 2100.0, "Spring fertiliser", "Co-op Store"),
        ("expense", "veterinary", 480.0, "Herd health visit", "Cahir Vet"),
    ]
    for rec_type, cat, amt, desc, cpty in base_records:
        marker = f"{DEMO_MARKER} {desc}"
        if not _has_record(existing_records, marker):
            add_financial_record(farm_file, {
                "record_type": rec_type, "date": date, "category": cat,
                "amount": amt, "description": marker, "counterparty": cpty,
            })
            created["records"] += 1

    # ── Documents (base + household) ────────────────────────────────
    existing_docs = list_documents(farm_file)

    base_documents = [
        ("receipt", "expense", "Fuel Depot", 340.0, "fuel", "paid", "Diesel"),
        ("invoice", "expense", "Contractor Ltd", 1500.0, "contractor", "unpaid", "Silage contractor"),
    ]
    all_documents = base_documents + [
        (dt, rt, cp, amt, cat, ps, ns) for dt, rt, cp, amt, cat, ps, ns in HOUSEHOLD_DOCUMENTS
    ]
    for doc_type, rec_type, cpty, amt, cat, pay_st, notes_suffix in all_documents:
        marker = f"{DEMO_MARKER} {notes_suffix}"
        if not _has_document(existing_docs, marker):
            add_document(farm_file, {
                "document_type": doc_type, "record_type": rec_type, "date": date,
                "counterparty": cpty, "amount": amt, "category": cat,
                "payment_status": pay_st, "notes": marker,
            })
            created["documents"] += 1

    # ── Category budgets ────────────────────────────────────────────
    if not list_category_budgets(farm_file, year=year):
        for rec_type, cat, amt, label in [
            ("income", "milk", 16000.0, "Milk budget"),
            ("expense", "feed", 4500.0, "Feed budget"),
            ("expense", "fertiliser", 1800.0, "Fertiliser budget"),
        ]:
            set_monthly_budget(farm_file, {
                "record_type": rec_type, "category": cat, "year": year, "month": month,
                "amount": amt, "notes": f"{DEMO_MARKER} {label}",
            })
            created["budgets"] += 1

    seeded = any(v > 0 for v in created.values())
    result = {"farm_file": farm_file, "seeded": seeded, "demo_month": f"{year:04d}-{month:02d}", "created": created}
    if not seeded:
        result["reason"] = "all demo data already present"
    return result


def maybe_seed_on_startup() -> None:
    """Called from API startup when FARMBIDDY_SEED_DEMO=1 (demo deployments)."""
    if os.environ.get("FARMBIDDY_SEED_DEMO", "").strip() != "1":
        return
    try:
        seed_demo_farm(os.environ.get("FARMBIDDY_DEMO_FARM", DEFAULT_FARM))
    except Exception:
        logging.getLogger("farmbiddy").exception("Demo farm seed skipped")
        return


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--farm-file", default=DEFAULT_FARM)
    args = parser.parse_args(argv)
    print(seed_demo_farm(args.farm_file))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
