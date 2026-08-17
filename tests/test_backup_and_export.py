"""P3.7 - backup/export/restore capability tests."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

import repositories.category_budgets as budgets_repo
import repositories.documents as documents_repo
import repositories.financial_records as records_repo
import repositories.onboarding as onboarding_repo
import scripts.backup_database as backup_db
import scripts.farm_data_export as farm_export
from config.settings import backend_for

FARM = "backup_test_farm.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch, isolated_db):
    # `farm_export._farm_profile` always reads/creates a `Farm` row (it is
    # farm-metadata, not one of the per-domain JSON/DB feature flags), so
    # every test here - JSON-backend or DB-backend - needs an isolated
    # database, not just the DB-backend test class.
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    monkeypatch.setattr(onboarding_repo, "ONBOARDING_DIR", str(tmp_path / "onboarding"))
    yield tmp_path


def _seed_json_backed_farm(farm_file: str) -> None:
    from services.category_budget_service import set_monthly_budget
    from services.document_service import add_document
    from services.financial_record_service import add_financial_record

    add_financial_record(farm_file, {
        "record_type": "income", "date": "2026-01-15", "category": "milk",
        "amount": 5000.0, "description": "January milk cheque",
    })
    add_document(farm_file, {
        "document_type": "invoice", "record_type": "expense", "date": "2026-01-10",
        "counterparty": "Feed Co", "amount": 800.0, "category": "feed",
        "payment_status": "paid", "description": "Feed invoice",
    })
    set_monthly_budget(farm_file, {
        "sector": None, "record_type": "expense", "category": "feed",
        "year": 2026, "month": 1, "amount": 750.0,
    })


class TestFarmDataExportJsonBackend:
    def test_export_captures_records_documents_and_budgets(self):
        _seed_json_backed_farm(FARM)

        data = farm_export.export_farm(FARM)

        assert data["farm_file"] == FARM
        assert len(data["financial_records"]) == 2  # manual income + document-linked expense
        assert len(data["documents"]) == 1
        assert len(data["category_budgets"]) == 1
        assert data["loans"] is None  # JSON backend: "no DB rows recorded" sentinel

    def test_write_export_then_restore_round_trips_into_a_fresh_farm(self, tmp_path):
        _seed_json_backed_farm(FARM)
        export_path = farm_export.write_export(FARM, str(tmp_path / "export.json"))
        assert os.path.exists(export_path)

        with open(export_path, "r", encoding="utf-8") as fh:
            exported = json.load(fh)

        restored_farm = "restored_test_farm.json"
        summary = farm_export.restore_farm(exported, farm_file=restored_farm)

        assert summary["financial_records"] == 2
        assert summary["documents"] == 1
        assert summary["category_budgets"] == 1

        from services.financial_record_service import list_financial_records
        assert len(list_financial_records(restored_farm)) == 2


class TestFarmDataExportDbBackend:
    @pytest.fixture(autouse=True)
    def db_backend(self, isolated_db, monkeypatch):
        monkeypatch.setenv("PERSISTENCE_BACKEND", "db")
        assert backend_for("FINANCIAL_RECORDS") == "db"

    def test_export_includes_farm_profile_and_restores_into_a_new_farm(self):
        farm_file = "db_backup_farm.json"
        _seed_json_backed_farm(farm_file)

        from db.session import session_scope
        from identity.seed import get_or_create_farm

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            farm.name = "My Test Farm"
            farm.sectors = ["dairy"]

        data = farm_export.export_farm(farm_file)
        assert data["farm_profile"]["name"] == "My Test Farm"
        assert data["farm_profile"]["sectors"] == ["dairy"]
        assert len(data["financial_records"]) == 2

        restored_farm = "db_restored_farm.json"
        summary = farm_export.restore_farm(data, farm_file=restored_farm)
        assert summary["farm_profile_restored"] is True
        assert summary["financial_records"] == 2

        with session_scope() as session:
            restored = get_or_create_farm(session, restored_farm)
            assert restored.name == "My Test Farm"
            assert restored.sectors == ["dairy"]


class TestSqliteDatabaseBackup:
    def test_backup_and_restore_round_trip(self, tmp_path, monkeypatch):
        source_db = tmp_path / "source.db"
        conn = sqlite3.connect(source_db)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO t (value) VALUES ('hello')")
        conn.commit()
        conn.close()

        monkeypatch.setattr(backup_db, "DATABASE_URL", f"sqlite:///{source_db.as_posix()}")
        monkeypatch.setattr(backup_db, "IS_SQLITE", True)

        backup_dir = tmp_path / "backups"
        backup_path = backup_db.backup_sqlite_database(str(backup_dir))
        assert os.path.exists(backup_path)

        target_db = tmp_path / "target.db"
        restored_path = backup_db.restore_sqlite_database(backup_path, str(target_db))

        conn = sqlite3.connect(restored_path)
        rows = conn.execute("SELECT value FROM t").fetchall()
        conn.close()
        assert rows == [("hello",)]

    def test_backup_raises_clear_error_for_non_sqlite_database(self, monkeypatch):
        monkeypatch.setattr(backup_db, "IS_SQLITE", False)
        monkeypatch.setattr(backup_db, "DATABASE_URL", "postgresql://example/db")

        with pytest.raises(backup_db.NotSupportedError):
            backup_db.backup_sqlite_database()
