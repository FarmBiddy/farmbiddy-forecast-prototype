# Persistence source-of-truth rules (P3.10 / P4.1)

This is the authoritative answer to "where does this data actually live
right now, and under what condition would that change?" for every mutable
farm-data domain.

## Current default: the database is authoritative for mutable farm data

`config/settings.backend_for(domain)` defaults every domain to `"db"`
(P4.1). JSON repository implementations remain in the codebase as
migration/rollback support - they are **not** deleted. Set
`PERSISTENCE_BACKEND=json` (or `PERSISTENCE_BACKEND_<DOMAIN>=json`) to
revert a domain without a code deploy. JSON files are never deleted by
cutting a domain over to `db`.

Parity with the previous JSON path is covered by
`tests/test_repository_backend_parity.py`.

## Per-domain status

| Domain | Authoritative store (P4.1) | JSON rollback location | Migration | Parity tests | Cutover flag |
|---|---|---|---|---|---|
| Financial records | `financial_records` table | `outputs/farm_events/financial_records/<farm>.json` | `scripts/migrate_json_to_db.py` | `TestFinancialRecordsParity` | `PERSISTENCE_BACKEND_FINANCIAL_RECORDS` |
| Documents | `documents` table | `outputs/farm_events/documents/<farm>.json` | `scripts/migrate_json_to_db.py` | `TestDocumentsParity` | `PERSISTENCE_BACKEND_DOCUMENTS` |
| Category budgets | `category_budgets` table | `outputs/farm_events/category_budgets/<farm>.json` | `scripts/migrate_json_to_db.py` | `TestCategoryBudgetsParity` | `PERSISTENCE_BACKEND_CATEGORY_BUDGETS` |
| Onboarding profile | `onboarding_profiles` table | `outputs/farm_events/onboarding/<farm>.json` | `scripts/migrate_json_to_db.py` | `TestOnboardingParity` | `PERSISTENCE_BACKEND_ONBOARDING` |
| Loans | `loans` table when rows exist; otherwise dataset-embedded `farm_summary.loans` | *(none - never a writable JSON store)* | `scripts/migrate_json_to_db.py` (dataset-embedded loans only) | migration reconciliation | `PERSISTENCE_BACKEND_LOANS` |
| Users / Farms / Memberships | `users`, `farms`, `farm_memberships` | *(none - always DB)* | n/a | `test_farm_isolation.py` | always active |

Rollback: `PERSISTENCE_BACKEND=json` or `PERSISTENCE_BACKEND_<DOMAIN>=json`.
No code deploy required; existing JSON files are left in place.

### Loans - the one true exception, not a gap

The **canonical sample dataset**'s embedded `loans` array
(`datasets/multi_sector_farm.json`) remains the fallback when a farm has
no `loans` table rows. `JsonLoanRepository.load()` / empty-DB
`DbLoanRepository.load()` return `None` (distinct from `[]`) as that
sentinel. Once DB rows exist they overlay the dataset via
`_overlay_persisted_loans` in `services/multi_sector_farm.py`.

## The canonical sample dataset is not "data to migrate"

`datasets/multi_sector_farm.json` is committed, read-only reference/demo
data - it is the *input* the forecast engine reads for historical actuals
and forecast assumptions for the shipped demo farm, not a farmer's mutable
records. P3 does not import it into `financial_records`/`category_budgets`
as if a farmer had typed it in; doing so would double count it against
genuinely farmer-entered data. `dataset_coverage_cutoff` (P1) remains the
explicit rule for where the dataset's historical coverage ends and
farmer-entered Actuals begin - P3 does not change or replace it. The
migration script only pulls the dataset's embedded `loans` array into the
`loans` table (see above), and only when `PERSISTENCE_BACKEND_LOANS=db`.

## Cutover (executed in P4.1)

All five mutable domains default to `"db"`. JSON paths remain as rollback.

Loans stay dual-source by design: `DbLoanRepository.load()` returns `None`
when a farm has no loan rows, and `services.multi_sector_farm` then keeps
using the sample dataset's embedded loans. Once
`scripts/migrate_json_to_db.py --apply` (or a farmer-owned write) creates
loan rows, those DB rows overlay the dataset.

Existing JSON farm-event files (if any) can still be imported with:

```bash
python -m scripts.migrate_json_to_db --farm-file multi_sector_farm.json --dry-run
python -m scripts.migrate_json_to_db --farm-file multi_sector_farm.json --apply
```

Take a backup first (see `docs/backup_and_recovery.md`).

## SQLite/PostgreSQL portability review

Every ORM type in `db/orm_models.py` (`Numeric`, `String`, `Text`, `Date`,
`DateTime(timezone=True)`, `JSON`, `CheckConstraint`, `ForeignKey`,
`UniqueConstraint`) is a generic SQLAlchemy type that compiles to the
appropriate native PostgreSQL type - none of it is SQLite-specific. All
SQLite-only code is isolated to two places, both intentional and
documented at the point of use:

* `db/session.py`'s `_connect_args` (`check_same_thread`) and the
  pytest-only auto-`init_db()` guard;
* `scripts/backup_database.py`, which is explicitly SQLite-only (see
  `docs/backup_and_recovery.md` for why Postgres backup is intentionally
  out of scope for this script).

**One real gap found and fixed during this review:** SQLite does not
enforce `FOREIGN KEY` constraints unless a connection explicitly turns it
on; PostgreSQL always enforces them. `db/session.enable_sqlite_foreign_keys`
now issues `PRAGMA foreign_keys=ON` on every new SQLite connection (a
no-op for Postgres), so a bug that tries to insert an orphaned row (e.g. a
`FinancialRecord.farm_id` or `FarmMembership.user_id` with no matching
parent row) fails the same way in local dev/tests as it would in
production, instead of silently succeeding locally and only surfacing
after a production deploy. Fixing this immediately caught one instance of
exactly that bug in a test's setup (a fabricated `RequestIdentity.user_id`
with no backing `User` row - see `tests/test_farm_isolation.py`).

No other SQLite-specific limitation is currently known. `UniqueConstraint`
and `CheckConstraint` behave identically on both engines for the
constraints actually defined here (simple column combinations and
`IN (...)` value lists).

## Identity / access control

`users`, `farms`, and `farm_memberships` are P3-native - they did not
exist as JSON before, so there is no "source of truth migration" question
for them, only the documented fact that `identity/context.DevIdentityProvider`
is an explicitly-marked development placeholder (single seeded user,
auto-enrols dataset-backed farms as "owner") standing in for whatever
identity/farm claims the main FarmBiddy platform will eventually supply
via `identity/context.IdentityProvider` - see that module's docstring for
the swap-out contract.
