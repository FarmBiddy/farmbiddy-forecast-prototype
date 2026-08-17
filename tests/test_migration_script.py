"""Tests for the P3.3 JSON -> database migration script.

Verifies the migration is deterministic, repeatable/idempotent, and that its
own reconciliation check genuinely catches count/total mismatches rather
than always reporting success.
"""

from __future__ import annotations

import json

import pytest

import repositories.category_budgets as budgets_repo
import repositories.documents as documents_repo
import repositories.financial_records as records_repo
import repositories.onboarding as onboarding_repo
import scripts.migrate_json_to_db as migrate
from services.category_budget_service import set_monthly_budget
from services.document_service import add_document
from services.financial_record_service import add_financial_record
from services.onboarding_service import complete_onboarding

FARM = "migration_test_farm.json"


@pytest.fixture(autouse=True)
def isolated_json_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    monkeypatch.setattr(onboarding_repo, "ONBOARDING_DIR", str(tmp_path / "onboarding"))
    yield tmp_path


@pytest.fixture
def sample_dataset(tmp_path, monkeypatch):
    """A minimal dataset file with an embedded `farm_summary.loans`, so the
    migration script's loans path is exercised without depending on the
    real (and potentially-changing) sample dataset's figures."""
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    (dataset_dir / FARM).write_text(json.dumps({
        "farm_summary": {
            "loans": [
                {"lender": "Test Bank", "principal": 10000, "monthly_repayment": 200, "rate": 5.0, "maturity": "2030-01"},
                {"lender": "Test Credit Union", "principal": 5000, "monthly_repayment": 100, "rate": 6.0, "maturity": "2027-06"},
            ],
        },
    }), encoding="utf-8")
    monkeypatch.setattr(migrate, "DATASETS_DIR", str(dataset_dir))
    yield dataset_dir


def _seed_json_data():
    # A paid receipt automatically creates one linked FinancialRecord (see
    # services/document_service.py), so financial_records ends up with 3
    # rows (2 manual + 1 document-linked) totalling 5000+1200+300=6500.
    add_financial_record(FARM, {
        "record_type": "income", "date": "2026-01-15", "category": "milk", "amount": 5000.0,
        "description": "Milk cheque",
    })
    add_financial_record(FARM, {
        "record_type": "expense", "date": "2026-01-20", "category": "feed", "amount": 1200.0,
        "description": "Ration",
    })
    add_document(FARM, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-02-01",
        "counterparty": "Vet Clinic", "amount": 300.0, "category": "veterinary",
    })
    set_monthly_budget(FARM, {
        "record_type": "expense", "category": "feed", "year": 2026, "month": 1, "amount": 1000.0,
    })
    complete_onboarding(FARM, {
        "farm_type": "dairy", "income_items": [], "cost_items": [], "loan_items": [],
        "current_cash": 15000.0, "year": 2026,
    })


def test_dry_run_reports_source_counts_without_writing(isolated_db, sample_dataset):
    _seed_json_data()
    report = migrate.migrate_farm(FARM, apply=False)

    by_domain = {d.domain: d for d in report.domains}
    assert by_domain["financial_records"].source_count == 3
    assert by_domain["financial_records"].source_total == 6500.0
    assert by_domain["documents"].source_count == 1
    assert by_domain["category_budgets"].source_count == 1
    assert by_domain["onboarding"].source_count == 1
    assert by_domain["loans"].source_count == 2
    assert by_domain["loans"].source_total == 15000.0

    # Dry run must not write anything to the database.
    from repositories.financial_records import DbFinancialRecordRepository
    assert DbFinancialRecordRepository().load(FARM) == []


def test_apply_migrates_all_domains_and_reconciles(isolated_db, sample_dataset):
    _seed_json_data()
    report = migrate.migrate_farm(FARM, apply=True)

    assert report.ok, [
        (d.domain, d.source_count, d.dest_count, d.source_total, d.dest_total) for d in report.domains
    ]
    by_domain = {d.domain: d for d in report.domains}
    assert by_domain["financial_records"].dest_count == 3
    assert by_domain["financial_records"].dest_total == 6500.0
    assert by_domain["documents"].dest_count == 1
    assert by_domain["category_budgets"].dest_count == 1
    assert by_domain["onboarding"].dest_count == 1
    assert by_domain["loans"].dest_count == 2
    assert by_domain["loans"].dest_total == 15000.0


def test_migration_is_idempotent_on_rerun(isolated_db, sample_dataset):
    _seed_json_data()
    migrate.migrate_farm(FARM, apply=True)
    first = migrate.migrate_farm(FARM, apply=True)
    assert first.ok

    from repositories.financial_records import DbFinancialRecordRepository
    from repositories.loans import DbLoanRepository

    # Re-running must not duplicate rows.
    assert len(DbFinancialRecordRepository().load(FARM)) == 3
    assert len(DbLoanRepository().load(FARM)) == 2


def test_farm_without_dataset_file_skips_loans_without_error(isolated_db, sample_dataset):
    other_farm = "no_dataset_farm.json"
    add_financial_record(other_farm, {
        "record_type": "income", "date": "2026-01-01", "category": "other_income", "amount": 100.0,
    })
    report = migrate.migrate_farm(other_farm, apply=True)
    assert report.ok
    loans_domain = next(d for d in report.domains if d.domain == "loans")
    assert loans_domain.source_count == 0
    assert "skipped" in loans_domain.detail


def test_reconciliation_flags_a_genuine_mismatch(isolated_db, sample_dataset, monkeypatch):
    _seed_json_data()

    from repositories.financial_records import DbFinancialRecordRepository

    original_load = DbFinancialRecordRepository.load

    def _tampered_load(self, farm_file):
        rows = original_load(self, farm_file)
        return rows[:-1] if rows else rows  # simulate a row silently lost in transit

    monkeypatch.setattr(DbFinancialRecordRepository, "load", _tampered_load)

    report = migrate.migrate_farm(FARM, apply=True)
    assert not report.ok
    financial_records_domain = next(d for d in report.domains if d.domain == "financial_records")
    assert not financial_records_domain.ok
