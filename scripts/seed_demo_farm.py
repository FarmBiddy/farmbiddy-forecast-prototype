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


def _already_seeded(farm_file: str) -> bool:
    from services.financial_record_service import list_financial_records

    return any(DEMO_MARKER in (r.get("description") or "") for r in list_financial_records(farm_file))


def _cutoff_year_month(farm_file: str) -> tuple[int, int]:
    from services.dashboard_summary import dataset_coverage_cutoff
    from services.multi_sector_farm import load_multi_sector_farm

    cutoff = dataset_coverage_cutoff(load_multi_sector_farm(farm_file))
    if cutoff:
        return cutoff
    return (2025, 8)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def seed_demo_farm(farm_file: str = DEFAULT_FARM) -> dict:
    """Write demo farmer-owned data through live services. Safe to re-run."""
    from config.settings import IS_SQLITE
    from db.session import init_db
    from services.category_budget_service import list_category_budgets, set_monthly_budget
    from services.document_service import add_document, list_documents
    from services.financial_record_service import add_financial_record

    if IS_SQLITE:
        init_db()

    if _already_seeded(farm_file):
        return {"farm_file": farm_file, "seeded": False, "reason": "already seeded"}

    year, month = _next_month(*_cutoff_year_month(farm_file))
    date = f"{year:04d}-{month:02d}-12"

    add_financial_record(farm_file, {
        "record_type": "income", "date": date, "category": "milk",
        "amount": 18500.0, "description": f"{DEMO_MARKER} Milk cheque",
        "counterparty": "Lakeland Dairies",
    })
    add_financial_record(farm_file, {
        "record_type": "income", "date": date, "category": "livestock",
        "amount": 4200.0, "description": f"{DEMO_MARKER} Finished cattle sale",
        "counterparty": "Mart",
    })
    add_financial_record(farm_file, {
        "record_type": "expense", "date": date, "category": "feed",
        "amount": 6200.0, "description": f"{DEMO_MARKER} Ration delivery",
        "counterparty": "Co-op Store",
    })
    add_financial_record(farm_file, {
        "record_type": "expense", "date": date, "category": "fertiliser",
        "amount": 2100.0, "description": f"{DEMO_MARKER} Spring fertiliser",
        "counterparty": "Co-op Store",
    })
    add_financial_record(farm_file, {
        "record_type": "expense", "date": date, "category": "veterinary",
        "amount": 480.0, "description": f"{DEMO_MARKER} Herd health visit",
        "counterparty": "Cahir Vet",
    })

    if not any(DEMO_MARKER in (d.get("notes") or "") for d in list_documents(farm_file)):
        add_document(farm_file, {
            "document_type": "receipt", "record_type": "expense", "date": date,
            "counterparty": "Fuel Depot", "amount": 340.0, "category": "fuel",
            "payment_status": "paid", "notes": f"{DEMO_MARKER} Diesel",
        })
        add_document(farm_file, {
            "document_type": "invoice", "record_type": "expense", "date": date,
            "counterparty": "Contractor Ltd", "amount": 1500.0, "category": "contractor",
            "payment_status": "unpaid", "notes": f"{DEMO_MARKER} Silage contractor",
        })

    if not list_category_budgets(farm_file, year=year):
        set_monthly_budget(farm_file, {
            "record_type": "income", "category": "milk", "year": year, "month": month,
            "amount": 16000.0, "notes": f"{DEMO_MARKER} Milk budget",
        })
        set_monthly_budget(farm_file, {
            "record_type": "expense", "category": "feed", "year": year, "month": month,
            "amount": 4500.0, "notes": f"{DEMO_MARKER} Feed budget",
        })
        set_monthly_budget(farm_file, {
            "record_type": "expense", "category": "fertiliser", "year": year, "month": month,
            "amount": 1800.0, "notes": f"{DEMO_MARKER} Fertiliser budget",
        })

    return {"farm_file": farm_file, "seeded": True, "demo_month": f"{year:04d}-{month:02d}"}


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
