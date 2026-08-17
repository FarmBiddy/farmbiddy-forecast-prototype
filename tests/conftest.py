"""Shared pytest fixtures for the P3 database-backed test suites."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.session as db_session


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """A fresh SQLite database, isolated per test, wired into `db.session` so
    every repository/service under test (via `session_scope`/`get_db`) uses
    it instead of the shared dev database file."""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", session_local)
    db_session.Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
