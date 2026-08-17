"""
P3.7 - Database backup/recovery for the local SQLite development database.

Scope, deliberately: this project's SQLite file (`outputs/farmbiddy.db` by
default) is the "production" database of a standalone prototype. This
script gives it one thing it did not have before: a documented, tested way
to produce a point-in-time, restorable copy of the whole database, using
SQLite's own online backup API (`sqlite3.Connection.backup`) rather than a
raw file copy - a raw copy of a live SQLite file can capture a half-written
page; the backup API cannot, because it goes through SQLite's own locking.

Production (PostgreSQL, per `config.settings.DATABASE_URL` /
`DEPLOYMENT.md`) is explicitly out of scope here: a managed Postgres host
(e.g. Render) already provides its own automated backup/point-in-time-
recovery strategy, and reimplementing that inside the application would be
exactly the "unnecessarily elaborate disaster-recovery system" the P3 brief
says not to build. `backup_sqlite_database` raises `NotSupportedError` for
a non-SQLite `DATABASE_URL` so that is a loud, explicit fact rather than a
silent no-op - see the module docstring in `docs/backup_and_recovery.md`
for the full documented recovery path (including the Postgres case).

Usage:
    python -m scripts.backup_database backup [--output-dir DIR]
    python -m scripts.backup_database restore <backup_file> [--target PATH]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.paths import STORAGE_ROOT
from config.settings import DATABASE_URL, IS_SQLITE

DEFAULT_BACKUP_DIR = os.path.join(STORAGE_ROOT, "backups", "db")


class NotSupportedError(RuntimeError):
    """Raised when a backup/restore operation is attempted against a
    non-SQLite `DATABASE_URL` (see module docstring)."""


def _sqlite_path_from_url(database_url: str) -> str:
    # "sqlite:///relative/path.db" or "sqlite:////absolute/path.db"
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise NotSupportedError(f"Not a SQLite URL: {database_url!r}")
    return database_url[len(prefix):]


def backup_sqlite_database(output_dir: str | None = None) -> str:
    """Create a timestamped, consistent copy of the SQLite database file
    using SQLite's own backup API. Returns the path to the new backup file.
    """
    if not IS_SQLITE:
        raise NotSupportedError(
            f"DATABASE_URL is not SQLite ({DATABASE_URL!r}); use the hosting "
            "provider's managed Postgres backup/point-in-time-recovery instead "
            "(see docs/backup_and_recovery.md).",
        )
    source_path = _sqlite_path_from_url(DATABASE_URL)
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"No database file found at {source_path!r} - nothing to back up yet.")

    output_dir = output_dir or DEFAULT_BACKUP_DIR
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(output_dir, f"farmbiddy_backup_{timestamp}.db")

    source_conn = sqlite3.connect(source_path)
    try:
        dest_conn = sqlite3.connect(backup_path)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    return backup_path


def restore_sqlite_database(backup_path: str, target_path: str | None = None) -> str:
    """Restore a previously-created backup file over `target_path` (default:
    the current `DATABASE_URL`'s SQLite file). The existing target, if any,
    is itself backed up first (suffixed `.pre_restore`) so a bad restore is
    never destructive-only.
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path!r}")

    target_path = target_path or _sqlite_path_from_url(DATABASE_URL)
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)

    if os.path.exists(target_path):
        shutil.copy2(target_path, f"{target_path}.pre_restore")

    backup_conn = sqlite3.connect(backup_path)
    try:
        target_conn = sqlite3.connect(target_path)
        try:
            backup_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        backup_conn.close()

    return target_path


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a new timestamped backup")
    backup_parser.add_argument("--output-dir", default=None)

    restore_parser = subparsers.add_parser("restore", help="Restore a backup file")
    restore_parser.add_argument("backup_file")
    restore_parser.add_argument("--target", default=None)

    args = parser.parse_args(argv)

    if args.command == "backup":
        path = backup_sqlite_database(args.output_dir)
        print(f"Backup written to: {path}")
    elif args.command == "restore":
        path = restore_sqlite_database(args.backup_file, args.target)
        print(f"Database restored to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
