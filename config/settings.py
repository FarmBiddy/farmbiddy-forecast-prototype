"""
P3 runtime configuration: database URL and per-domain persistence backend
feature flags.

Nothing here changes farmer-visible behaviour by default beyond what P3
explicitly migrates. Every setting is an environment variable with a safe
local-dev default so `pytest`/local `uvicorn` need zero configuration.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine.url import make_url

from config.paths import STORAGE_ROOT

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
# Local/dev default: a SQLite file inside the existing writable STORAGE_ROOT
# (same root as outputs/farm_events/...), so no extra configuration is needed
# to run the app or test suite locally.
#
# Production: set DATABASE_URL to a PostgreSQL connection string (Render's
# managed Postgres, or any other host). The application code never branches
# on "sqlite vs postgres" beyond this one place plus the engine's
# connect_args - all business logic goes through the same SQLAlchemy ORM.
_default_sqlite_path = Path(STORAGE_ROOT) / "farmbiddy.db"


def prepare_database_url(url: str) -> str:
    """Return a connectable database URL.

    File-backed SQLite: resolve an absolute path and create the parent
    directory *before* SQLAlchemy opens a connection. Postgres, SQLite
    ``:memory:``, and empty URLs are returned unchanged — no filesystem
    work.

    Render's checkout does not include ``outputs/`` (the ``.db`` file is
    gitignored and the folder is not committed). Without this, startup
    fails with ``sqlite3.OperationalError: unable to open database file``.
    """
    url = (url or "").strip()
    if not url:
        return url
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return url
    database = parsed.database
    if not database or database == ":memory:":
        return url
    path = Path(database).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(parsed.set(database=path.as_posix()))


_raw_database_url = os.environ.get("DATABASE_URL", "").strip()
DATABASE_URL = prepare_database_url(
    _raw_database_url or f"sqlite:///{_default_sqlite_path.as_posix()}"
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")


# ---------------------------------------------------------------------------
# Per-domain persistence backend flags ("json" | "db")
# ---------------------------------------------------------------------------
# Each mutable farm-data domain can be cut over to the database independently
# and rolled back independently by flipping one environment variable, per the
# approved P3 "dual-path repository" design. PERSISTENCE_BACKEND sets the
# default for all domains at once; PERSISTENCE_BACKEND_<DOMAIN> overrides it
# for just that domain, e.g. PERSISTENCE_BACKEND_DOCUMENTS=db to cut over
# just documents while everything else stays on JSON.
#
# P4.1: the shipped default is "db" - the database is the normal persistence
# path for mutable farmer-owned data. JSON implementations remain in the
# repository layer as migration/rollback support: set PERSISTENCE_BACKEND=json
# (or PERSISTENCE_BACKEND_<DOMAIN>=json) to revert a domain without a code
# deploy. See docs/persistence_source_of_truth.md.
#
# Read live (not cached at import) so tests and ops tooling can flip a
# domain's backend by setting an environment variable without reimporting
# every module that already resolved a repository.
_DOMAINS = (
    "FINANCIAL_RECORDS",
    "DOCUMENTS",
    "CATEGORY_BUDGETS",
    "ONBOARDING",
    "LOANS",
)


def backend_for(domain: str) -> str:
    """'json' or 'db' for one persistence domain (see _DOMAINS above)."""
    domain = domain.upper()
    global_default = os.environ.get("PERSISTENCE_BACKEND", "db").strip().lower()
    if global_default not in ("json", "db"):
        global_default = "db"
    value = os.environ.get(f"PERSISTENCE_BACKEND_{domain}", global_default).strip().lower()
    return value if value in ("json", "db") else global_default


# ---------------------------------------------------------------------------
# Identity provider ("dev" today; a future real-platform adapter later)
# ---------------------------------------------------------------------------
IDENTITY_PROVIDER = os.environ.get("IDENTITY_PROVIDER", "dev").strip().lower()
