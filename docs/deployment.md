# Deployment (Prototype v1)

This is the FarmBiddy **financial prototype**, not a paid production estate.
Use it for demos and integration evaluation.

Local SQLite creates tables on app startup (`init_db`). Import-time auto-init
still respects `FARMBIDDY_AUTO_INIT_DB` (tests set this to `0`).

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 — Farmer Edition UI. API docs: `/docs`.

Defaults (no extra config):

- SQLite at `outputs/farmbiddy.db`
- `PERSISTENCE_BACKEND=db` for mutable farm data
- `IDENTITY_PROVIDER=dev`
- JSON rollback still available (`PERSISTENCE_BACKEND=json`)

Optional demo records (invoices, extra actuals, budgets) through live services:

```bash
set FARMBIDDY_SEED_DEMO=1
python -m scripts.seed_demo_farm
```

Or set `FARMBIDDY_SEED_DEMO=1` in the environment so startup seeds once.

## Demo deployment (Render)

Current intended mode: **ephemeral SQLite on the instance filesystem**.
There is **no** persistent disk and **no** Postgres on the free demo.

`render.yaml`:

- `buildCommand`: `pip install -r requirements.txt`
- `startCommand`: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- health check: `/api/status`

### Required / recommended env (already in `render.yaml`)

| Variable | Value | Notes |
|---|---|---|
| `PERSISTENCE_BACKEND` | `db` | Mutable farm data in SQLite |
| `IDENTITY_PROVIDER` | `dev` | Prototype identity adapter |
| `FARMBIDDY_SEED_DEMO` | `1` | Seed `[DEMO]` records on first start |

**Leave `DATABASE_URL` unset** unless you are pointing at Postgres. The default is SQLite at `{app}/outputs/farmbiddy.db` (absolute). The app creates `outputs/` if it is missing — that directory is not in git.

Do **not** set `STORAGE_PATH=/opt/render/project/data` unless a Render disk is actually mounted at that path.

### Startup sequence (SQLite demo)

1. Resolve `DATABASE_URL`; for file SQLite, create the parent directory and use an absolute path.
2. Import-time `init_db()` (`create_all`) so a fresh file has tables. Skip under pytest.
3. FastAPI startup: `ensure_output_dirs()`, `init_db()` again (idempotent), then `maybe_seed_on_startup()` if `FARMBIDDY_SEED_DEMO=1`.
4. Sample farm JSON comes from committed `datasets/`; farmer-owned demo rows are seeded through normal services.

No pre-created `farmbiddy.db` is required. **Alembic is not run on this SQLite demo.** Use `alembic upgrade head` only for Postgres.

### Persistence is ephemeral

Render’s instance disk is **not durable**. SQLite, generated reports/charts, and seeded demo rows **reset on deploy, restart, or host move**. Dataset sample history is restored from git; `FARMBIDDY_SEED_DEMO=1` re-seeds extra demo records.

For **durable** data later (needs approval / paid plan): mount a disk and set `STORAGE_PATH` to the mount, **or** set `DATABASE_URL` to Postgres and run `alembic upgrade head` as a deploy step.

## Database migrations

Local / Render SQLite: tables via `init_db()` (`create_all`) on import and startup (`FARMBIDDY_AUTO_INIT_DB=1`). Tests set this to `0` and use an isolated temp file.

Production Postgres:

```bash
alembic upgrade head
```

New schema changes go in `alembic/versions/`, never `create_all` in prod.

Existing JSON farm-event files:

```bash
python -m scripts.migrate_json_to_db --dry-run
python -m scripts.migrate_json_to_db --apply
```

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL. Default: SQLite under `STORAGE_ROOT` |
| `STORAGE_PATH` | Writable root for outputs/db/backups |
| `PERSISTENCE_BACKEND` | `db` (default) or `json` rollback |
| `PERSISTENCE_BACKEND_<DOMAIN>` | Per-domain override |
| `IDENTITY_PROVIDER` | `dev` today |
| `FARMBIDDY_AUTO_INIT_DB` | `1` (default) SQLite `create_all`; `0` in migration tests |
| `FARMBIDDY_SEED_DEMO` | `1` to seed demo farmer-owned data on startup |
| `FARMBIDDY_DEMO_FARM` | farm file for that seed (default `multi_sector_farm.json`) |

See `.env.example`. Never commit secrets.

## Backup

SQLite: `python -m scripts.backup_database backup`

Farm export: `python -m scripts.farm_data_export export multi_sector_farm.json`
or `GET /api/farmer/farm-data/export` (membership required).

Postgres: use the host's backup/PITR. Details: `docs/backup_and_recovery.md`.

## Rollback

1. Persistence: set `PERSISTENCE_BACKEND=json` (JSON files were not deleted).
2. Schema: `alembic downgrade <rev>` (know the implications).
3. Data: restore a SQLite backup or farm export.

## Known prototype limitations

- No standalone email/password login (`DevIdentityProvider` only).
- No real OCR, bank feed or accounting integration.
- `financial_engine/` is unused; `forecast_engine/` is authoritative.
- Demo farm is labelled SAMPLE / DEMO — not a real farm.
- Dual-path JSON repositories remain for rollback, not as a second product.
