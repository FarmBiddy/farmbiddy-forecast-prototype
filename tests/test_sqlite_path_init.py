"""SQLite parent-directory bootstrap (Render: unable to open database file)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from config.settings import prepare_database_url


def test_prepare_creates_missing_parent_and_connection_succeeds(tmp_path):
    db_path = tmp_path / "nested" / "missing" / "farmbiddy.db"
    assert not db_path.parent.exists()

    url = prepare_database_url(f"sqlite:///{db_path.as_posix()}")
    assert db_path.parent.is_dir()
    assert Path(db_path).name == "farmbiddy.db"
    assert "missing" in url.replace("\\", "/")

    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        from db import orm_models  # noqa: F401
        from db.session import Base

        Base.metadata.create_all(bind=engine)
        assert db_path.is_file()
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='farms'")
            ).fetchall()
            assert tables
    finally:
        engine.dispose()


def test_prepare_resolves_relative_sqlite_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = Path("rel_outputs") / "farmbiddy.db"
    assert not relative.parent.exists()

    url = prepare_database_url(f"sqlite:///{relative.as_posix()}")
    assert (tmp_path / "rel_outputs").is_dir()
    resolved = (tmp_path / relative).resolve()
    assert resolved.as_posix() in url.replace("\\", "/")


def test_postgres_url_is_unchanged_and_creates_no_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    url = "postgresql+psycopg://farmbiddy:secret@localhost:5432/farmbiddy"
    assert prepare_database_url(url) == url
    assert not (tmp_path / "farmbiddy").exists()
    assert not (tmp_path / "outputs").exists()


def test_sqlite_memory_url_is_unchanged():
    assert prepare_database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_empty_url_is_unchanged():
    assert prepare_database_url("") == ""
    assert prepare_database_url("   ") == ""
