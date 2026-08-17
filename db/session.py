"""
SQLAlchemy engine/session bootstrap.

Local dev and the test suite use SQLite (zero configuration); production
sets `DATABASE_URL` to a PostgreSQL connection string. Everything below this
line is database-agnostic - no code elsewhere in the app should need to know
which one is in use.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import DATABASE_URL, IS_SQLITE

_connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model (see `db/orm_models.py`)."""


def init_db() -> None:
    """Create tables directly from the ORM metadata.

    This is a local-dev/test convenience only (SQLite starts from an empty
    file with no migration history to apply). Production deployments run
    `alembic upgrade head` as a deploy step instead - see `alembic/` and
    `render.yaml`. Calling this against a database already managed by
    Alembic is harmless (`create_all` skips tables that already exist) but
    is not how production schema changes should be made.
    """
    from db import orm_models  # noqa: F401  (ensures models are registered on Base.metadata)

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One transactional unit of work. Commits on success, rolls back and
    re-raises on any exception, always closes the session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency form of `session_scope`, for routes that want a
    session injected directly rather than going through a repository."""
    with session_scope() as session:
        yield session


_RUNNING_UNDER_PYTEST = "pytest" in sys.modules

if os.environ.get("FARMBIDDY_AUTO_INIT_DB", "1") == "1" and IS_SQLITE and not _RUNNING_UNDER_PYTEST:
    # Local/dev convenience: a fresh SQLite file gets its schema created
    # automatically on first import, matching the zero-configuration feel of
    # today's JSON storage. Disable with FARMBIDDY_AUTO_INIT_DB=0 (e.g. if a
    # migration step wants full control over schema creation).
    #
    # Never auto-touches the shared dev database file under pytest (detected
    # via `"pytest" in sys.modules`, which is already true by the time this
    # module is first imported through any conftest/test module - pytest
    # imports itself before collecting anything). Every test that needs a
    # database uses the `isolated_db` fixture's own temporary SQLite file
    # (see tests/conftest.py) instead - this is what makes concurrent test
    # processes (e.g. two `pytest` runs, or a background test job overlapping
    # a foreground one) unable to lock each other out of one shared file.
    init_db()
