"""
SQLAlchemy engine/session bootstrap.

Local dev and the test suite use SQLite (zero configuration); production
sets `DATABASE_URL` to a PostgreSQL connection string. Everything below this
line is database-agnostic - no code elsewhere in the app should need to know
which one is in use.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import DATABASE_URL, IS_SQLITE


def enable_sqlite_foreign_keys(target_engine: Engine) -> None:
    """SQLite does not enforce `FOREIGN KEY` constraints unless a session
    explicitly turns it on (`PRAGMA foreign_keys = ON`) - unlike PostgreSQL,
    where they are always enforced. Without this, a bug that inserts, say,
    a `financial_records` row with a `farm_id` that does not exist would
    silently succeed in SQLite (dev/test) and only be caught in production
    (Postgres) - exactly the kind of accidental SQLite-only behaviour the
    architecture is supposed to avoid. Applied to every new DBAPI
    connection this engine opens; a no-op for non-SQLite engines.
    """
    if not str(target_engine.url).startswith("sqlite"):
        return

    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# DATABASE_URL has already been through prepare_database_url (config.settings):
# file-backed SQLite parents exist and the path is absolute before connect.
_connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
enable_sqlite_foreign_keys(engine)
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


# Schema creation is FastAPI lifespan (`api.main.lifespan`), not import-time.
# Importing this module only constructs the engine. That is required so
# Uvicorn can finish loading the app and bind $PORT without waiting on
# create_all. Tests use the isolated_db fixture's own create_all.
