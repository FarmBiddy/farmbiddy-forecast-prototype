"""
P3.3 - JSON -> database migration.

Reads today's JSON-file storage (farm_events/financial_records,
farm_events/documents, farm_events/category_budgets, farm_events/onboarding,
plus the read-only dataset's embedded `farm_summary.loans`) and writes it
into the relational schema in `db/orm_models.py`, via the exact same
repository classes the application uses at runtime
(`repositories/*.DbXxxRepository`) - so migrated data and freshly-written
data always take the same path into the database.

Usage (from the repository root):

    python -m scripts.migrate_json_to_db --dry-run          # report only
    python -m scripts.migrate_json_to_db --apply             # write + verify
    python -m scripts.migrate_json_to_db --apply --farm-file multi_sector_farm.json

Every run (dry-run or apply) ends with a reconciliation report comparing
source (JSON) and destination (DB) counts and financial totals for each
domain. `--apply` exits non-zero if any domain's totals do not reconcile
after the write, so a bad migration is never silently declared successful.

Idempotency: this script can be re-run safely. Each domain's
`DbXxxRepository.save()` replaces that farm's full set of rows in one
transaction (matching the JSON file's "whole file" semantics - see
`repositories/financial_records.py`), so re-running the migration against
the same JSON input reproduces the same DB state rather than duplicating
rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("PERSISTENCE_BACKEND", "json")  # read source data via the JSON path below

from config.paths import (  # noqa: E402
    CATEGORY_BUDGETS_DIR,
    DATASETS_DIR,
    DOCUMENTS_DIR,
    FINANCIAL_RECORDS_DIR,
    ONBOARDING_DIR,
)


@dataclass
class DomainReport:
    domain: str
    source_count: int = 0
    dest_count: int = 0
    source_total: float = 0.0
    dest_total: float = 0.0
    ok: bool = True
    detail: str = ""


@dataclass
class FarmMigrationReport:
    farm_file: str
    domains: list[DomainReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(d.ok for d in self.domains)


def _discover_farm_files() -> list[str]:
    """Every farm_file with JSON data in any farm_events store, plus any
    dataset file in datasets/ (so a dataset-only farm with no manual entries
    yet still gets a Farm row + migrated loans)."""
    stems: set[str] = set()
    for directory in (FINANCIAL_RECORDS_DIR, DOCUMENTS_DIR, CATEGORY_BUDGETS_DIR, ONBOARDING_DIR):
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                if name.endswith(".json"):
                    stems.add(os.path.splitext(name)[0])
    if os.path.isdir(DATASETS_DIR):
        for name in os.listdir(DATASETS_DIR):
            if name.endswith(".json"):
                stems.add(os.path.splitext(name)[0])
    return sorted(f"{stem}.json" for stem in stems)


def _raw_dataset_loans(farm_file: str) -> list[dict] | None:
    path = os.path.join(DATASETS_DIR, farm_file)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return None
    loans = ((data or {}).get("farm_summary") or {}).get("loans")
    return loans if isinstance(loans, list) else []


def _migrate_financial_records(farm_file: str, apply: bool) -> DomainReport:
    from repositories.financial_records import DbFinancialRecordRepository, JsonFinancialRecordRepository

    source = JsonFinancialRecordRepository().load(farm_file)
    report = DomainReport(
        domain="financial_records",
        source_count=len(source),
        source_total=round(sum(float(r.get("amount") or 0) for r in source), 2),
    )
    if apply:
        DbFinancialRecordRepository().save(farm_file, source)
        dest = DbFinancialRecordRepository().load(farm_file)
        report.dest_count = len(dest)
        report.dest_total = round(sum(float(r.get("amount") or 0) for r in dest), 2)
        report.ok = report.dest_count == report.source_count and abs(report.dest_total - report.source_total) < 0.01
    return report


def _migrate_documents(farm_file: str, apply: bool) -> DomainReport:
    from repositories.documents import DbDocumentRepository, JsonDocumentRepository

    source = JsonDocumentRepository().load(farm_file)
    report = DomainReport(
        domain="documents",
        source_count=len(source),
        source_total=round(sum(float(d.get("amount") or 0) for d in source), 2),
    )
    if apply:
        DbDocumentRepository().save(farm_file, source)
        dest = DbDocumentRepository().load(farm_file)
        report.dest_count = len(dest)
        report.dest_total = round(sum(float(d.get("amount") or 0) for d in dest), 2)
        report.ok = report.dest_count == report.source_count and abs(report.dest_total - report.source_total) < 0.01
    return report


def _migrate_category_budgets(farm_file: str, apply: bool) -> DomainReport:
    from repositories.category_budgets import DbCategoryBudgetRepository, JsonCategoryBudgetRepository

    source = JsonCategoryBudgetRepository().load(farm_file)
    report = DomainReport(
        domain="category_budgets",
        source_count=len(source),
        source_total=round(sum(float(b.get("amount") or 0) for b in source), 2),
    )
    if apply:
        DbCategoryBudgetRepository().save(farm_file, source)
        dest = DbCategoryBudgetRepository().load(farm_file)
        report.dest_count = len(dest)
        report.dest_total = round(sum(float(b.get("amount") or 0) for b in dest), 2)
        report.ok = report.dest_count == report.source_count and abs(report.dest_total - report.source_total) < 0.01
    return report


def _migrate_onboarding(farm_file: str, apply: bool) -> DomainReport:
    from repositories.onboarding import DbOnboardingRepository, JsonOnboardingRepository

    source = JsonOnboardingRepository().load(farm_file)
    report = DomainReport(
        domain="onboarding",
        source_count=1 if source else 0,
        source_total=round(float(source.get("current_cash") or 0), 2) if source else 0.0,
    )
    if apply:
        if source:
            DbOnboardingRepository().save(farm_file, source)
        dest = DbOnboardingRepository().load(farm_file)
        report.dest_count = 1 if dest else 0
        report.dest_total = round(float(dest.get("current_cash") or 0), 2) if dest else 0.0
        report.ok = report.dest_count == report.source_count and abs(report.dest_total - report.source_total) < 0.01
    return report


def _migrate_loans(farm_file: str, apply: bool) -> DomainReport:
    from repositories.loans import DbLoanRepository

    raw_loans = _raw_dataset_loans(farm_file)
    if raw_loans is None:
        # No canonical dataset file for this farm_file (e.g. a farm created
        # purely through onboarding) - nothing to migrate, not an error.
        return DomainReport(domain="loans", detail="no dataset file - skipped")

    source_loans = [dict(loan, source="dataset_import") for loan in raw_loans]
    report = DomainReport(
        domain="loans",
        source_count=len(source_loans),
        source_total=round(sum(float(l.get("principal") or 0) for l in source_loans), 2),
    )
    if apply:
        DbLoanRepository().save(farm_file, source_loans)
        dest = DbLoanRepository().load(farm_file) or []
        report.dest_count = len(dest)
        report.dest_total = round(sum(float(l.get("principal") or 0) for l in dest), 2)
        report.ok = report.dest_count == report.source_count and abs(report.dest_total - report.source_total) < 0.01
    return report


def migrate_farm(farm_file: str, apply: bool = False) -> FarmMigrationReport:
    """Migrate one farm's JSON data into the database.

    Each domain helper below opens and commits its own short-lived
    `session_scope()` (via the same `DbXxxRepository` the application uses
    at runtime) rather than sharing one long-lived transaction across every
    domain - SQLite only allows one writer at a time, and holding an outer
    transaction open while each domain's repository opens its own nested
    connection would deadlock against it.
    """
    from db.session import session_scope
    from identity.seed import ensure_dev_owner, get_or_create_farm

    dataset_path = os.path.join(DATASETS_DIR, farm_file)
    has_dataset = os.path.exists(dataset_path)

    with session_scope() as session:
        farm = get_or_create_farm(
            session, farm_file,
            dataset_file=farm_file if has_dataset else None,
        )
        if apply:
            ensure_dev_owner(session, farm)

    report = FarmMigrationReport(farm_file=farm_file)
    report.domains.append(_migrate_financial_records(farm_file, apply))
    report.domains.append(_migrate_documents(farm_file, apply))
    report.domains.append(_migrate_category_budgets(farm_file, apply))
    report.domains.append(_migrate_onboarding(farm_file, apply))
    report.domains.append(_migrate_loans(farm_file, apply))
    return report


def _print_report(reports: list[FarmMigrationReport], apply: bool) -> bool:
    all_ok = True
    mode = "APPLY" if apply else "DRY RUN"
    print(f"\n=== JSON -> database migration ({mode}) ===")
    for farm_report in reports:
        print(f"\nFarm: {farm_report.farm_file}")
        for domain in farm_report.domains:
            if apply:
                status = "OK" if domain.ok else "MISMATCH"
                print(
                    f"  {domain.domain:<18} source={domain.source_count:>4} "
                    f"({domain.source_total:>12.2f})  dest={domain.dest_count:>4} "
                    f"({domain.dest_total:>12.2f})  [{status}]"
                )
            else:
                print(
                    f"  {domain.domain:<18} source={domain.source_count:>4} "
                    f"total={domain.source_total:>12.2f}  {domain.detail}"
                )
            if not domain.ok:
                all_ok = False
    print()
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--farm-file", help="Migrate only this farm_file (default: every farm with JSON data)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report source counts/totals only (default)")
    mode.add_argument("--apply", action="store_true", help="Write to the database and verify reconciliation")
    args = parser.parse_args()

    apply = bool(args.apply)
    farm_files = [args.farm_file] if args.farm_file else _discover_farm_files()
    if not farm_files:
        print("No farm JSON data found to migrate.")
        return 0

    reports = [migrate_farm(farm_file, apply=apply) for farm_file in farm_files]
    ok = _print_report(reports, apply)

    if apply and not ok:
        print("MIGRATION RECONCILIATION FAILED - see MISMATCH rows above.")
        return 1
    if apply:
        print("Migration complete and reconciled: source and destination totals match for every domain.")
    else:
        print("Dry run complete. Re-run with --apply to write to the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
