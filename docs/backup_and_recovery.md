# Backup and recovery (P3.7)

Two independent, tested tools exist. Neither is elaborate disaster-recovery
infrastructure - they are the minimum needed for "there is a documented path
to recovering financial records if persistence fails", per the P3 brief.

## 1. Whole-database backup - `scripts/backup_database.py`

Local/dev SQLite only (see below for production). Uses SQLite's own online
backup API (`sqlite3.Connection.backup`), not a raw file copy, so a backup
taken while the app is running is always internally consistent.

```bash
# Create a timestamped backup (default: outputs/backups/db/)
python -m scripts.backup_database backup

# Restore a backup over the live database (the existing file, if any, is
# itself saved first as <target>.pre_restore)
python -m scripts.backup_database restore outputs/backups/db/farmbiddy_backup_20260817T120000Z.db
```

**Production (PostgreSQL):** this script intentionally does not support
Postgres (`backup_sqlite_database` raises `NotSupportedError`). A managed
Postgres host (Render, etc. - see `DEPLOYMENT.md`) already provides
automated backups and point-in-time recovery; reimplementing that inside
the application would duplicate infrastructure the host already runs more
reliably. Use the host's backup/restore console or `pg_dump`/`pg_restore`
for production recovery.

**Schema versioning:** every schema change is an Alembic migration under
`alembic/versions/`. `alembic upgrade head` / `alembic downgrade <rev>`
is the versioning and rollback mechanism for the schema itself, independent
of data backups.

## 2. Per-farm data export/restore - `scripts/farm_data_export.py`

A portable, human-readable JSON snapshot of one farm's owned data
(financial records, documents, category budgets, loans, onboarding
profile, and farm profile), read and written through the exact same
repository interfaces the running application uses - so it is never a
second, drifting serialisation of the domain models.

```bash
# Export one farm (default output: outputs/backups/farm_exports/)
python -m scripts.farm_data_export export multi_sector_farm.json

# Restore it back (same farm_file = disaster recovery; a different
# farm_file = clone the data into a new farm, with ids regenerated to
# avoid colliding with the source farm's still-existing rows)
python -m scripts.farm_data_export restore outputs/backups/farm_exports/multi_sector_farm_20260817T120000Z.json
```

This also works across the JSON/DB persistence backends in either
direction (see `config/settings.backend_for`), since the export format is
just the repositories' own `load()` output - the same property that makes
`scripts/migrate_json_to_db.py` possible.

## What is *not* covered

* Automated/scheduled backups - there is no cron/CI job invoking either
  script yet. For the prototype, backups are an operator action; wiring a
  scheduled job is a reasonable production follow-up, not a P3 requirement.
* Point-in-time recovery within a day (only whole-database or whole-farm
  snapshots at the moment they are taken).
* Encryption/off-site replication of backup files - inherit whatever the
  deployment host already provides for its own storage.
