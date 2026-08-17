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
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{_default_sqlite_path.as_posix()}",
).strip()

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
# The shipped default is "json" - i.e. P3 adds real, tested, parity-checked
# relational persistence for every domain without silently changing what a
# fresh checkout or the existing test suite does. An operator flips this to
# "db" (after running `scripts/migrate_json_to_db.py`) to make the database
# authoritative; see the P3 completion report for the recommended rollout.
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
    global_default = os.environ.get("PERSISTENCE_BACKEND", "json").strip().lower()
    if global_default not in ("json", "db"):
        global_default = "json"
    value = os.environ.get(f"PERSISTENCE_BACKEND_{domain}", global_default).strip().lower()
    return value if value in ("json", "db") else global_default


# ---------------------------------------------------------------------------
# Identity provider ("dev" today; a future real-platform adapter later)
# ---------------------------------------------------------------------------
IDENTITY_PROVIDER = os.environ.get("IDENTITY_PROVIDER", "dev").strip().lower()
