# Prototype v1 — technical overview

FarmBiddy Financial Prototype v1 is a standalone farmer UI plus `/api` that the main FarmBiddy platform can call later. It is demo- and integration-ready, not a production identity or OCR product.

## Stack

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, SQLite locally / PostgreSQL-ready (`psycopg`), uvicorn. Frontend: static `frontend/` (HTML/JS/CSS) served by the same app. Reports: ReportLab PDFs.

## Architecture

```
Farmer UI  or  Main FarmBiddy Platform
        →  FastAPI (/api/…)
        →  IdentityProvider → RequestIdentity
        →  farm-scoped services + repositories
        →  forecast_engine (calculations)
        →  JSON / PDF / charts
```

`services/` orchestrate. Repositories persist. The UI does not embed financial formulas.

## Financial engine

**Authoritative:** `forecast_engine/` (revenue, costs, cash flow, scenarios, alerts consumed by services).

**Not on the live path:** `financial_engine/` — present in the tree, unused by Prototype v1 calculations. Do not treat it as the product engine.

Actual, Budget and Forecast stay separate. Farmer What If? uses the same engine with overridden inputs and does not write Actuals.

## Persistence

SQLAlchemy + Alembic. Default `PERSISTENCE_BACKEND=db` for mutable farmer data (records, documents, category budgets, onboarding, loans when rows exist). JSON repositories remain for migration/rollback only.

Canonical `datasets/*.json` is **sample/reference** history, not imported as FinancialRecords (`dataset_coverage_cutoff`). SQLite file: `outputs/farmbiddy.db` (created on startup). Postgres: set `DATABASE_URL`, run `alembic upgrade head`.

## API

Public surface: `/api/...` (OpenAPI `/docs`). The same router is also mounted at `/` for legacy clients — new integrations should use `/api`.

Principal groups: farm profile/onboarding, financial records, documents, category budgets, cash flow / dashboard, Budget vs Actual, loans summary, forecasts, What If? / cash-flow actions, alerts, reports, export.

## Farm isolation

`User` → `FarmMembership` → `Farm`. Mutable reads/writes go through `enforce_farm_access`. Proven by `tests/test_farm_isolation.py`.

## Identity seam

`IdentityProvider` protocol in `identity/context.py`. Today: `DevIdentityProvider` (`IDENTITY_PROVIDER=dev`). Replace later with a platform adapter that maps authenticated user + authorised farm + role onto `RequestIdentity`. No login/password system in this service.

## Tests

**431** passing (pytest, isolated temp SQLite per test). Covers services, repositories, JSON/SQL parity, migration reconcile, farm isolation, API routes, reports, demo seed.

## Current limitations

No real authentication. No OCR, bank or accounting provider (registry empty). Loan UI CRUD is limited. Engine still dairy-leaning for some assumptions. Not statutory accounts. Dual JSON path is rollback, not a second product.

## Future extension points

| Seam | Use later | Status now |
|---|---|---|
| `IdentityProvider` | Main platform JWT/gateway | Dev adapter only |
| `DocumentProvider` (`services/document_providers.py`) | OCR / bank / accounts import | Protocol only; farmer confirms before Actuals |
| Dairy statement provider factory | Processor statements | Mock/placeholder, not a live feed |
| `PERSISTENCE_BACKEND_*` | Rollback a domain to JSON | JSON not deleted |
| Postgres `DATABASE_URL` | Hosted demo / production | SQLite default |

Do not describe the rows above as shipped product behaviour.
