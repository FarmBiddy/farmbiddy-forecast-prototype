# Persistence source-of-truth rules (P3.10)

This is the authoritative answer to "where does this data actually live
right now, and under what condition would that change?" for every mutable
farm-data domain, after P3's database/repository/identity work.

## Current default: JSON remains authoritative

`config/settings.backend_for(domain)` defaults every domain to `"json"`.
**No file has been deleted or deprecated by P3.** The relational schema,
migration script, and DB-backed repositories exist, are tested, and are
proven to behave identically to the JSON path (`tests/test_repository_backend_parity.py`) - they are *available*, not yet *load-bearing*. This is
deliberate: the brief for this phase was explicit that legacy JSON paths
must not be removed "merely because a database exists", only once
migration is verified, no production path depends on them, and rollback
implications are understood. Today, JSON is still the production path.

## Per-domain status

| Domain | JSON location (authoritative today) | DB table (tested, not yet default) | Migration | Parity tests | Cutover flag |
|---|---|---|---|---|---|
| Financial records | `outputs/farm_events/financial_records/<farm>.json` | `financial_records` | `scripts/migrate_json_to_db.py` | `test_repository_backend_parity.py::TestFinancialRecordsParity` | `PERSISTENCE_BACKEND_FINANCIAL_RECORDS` |
| Documents | `outputs/farm_events/documents/<farm>.json` | `documents` | `scripts/migrate_json_to_db.py` | `TestDocumentsParity` | `PERSISTENCE_BACKEND_DOCUMENTS` |
| Category budgets | `outputs/farm_events/category_budgets/<farm>.json` | `category_budgets` | `scripts/migrate_json_to_db.py` | `TestCategoryBudgetsParity` | `PERSISTENCE_BACKEND_CATEGORY_BUDGETS` |
| Onboarding profile | `outputs/farm_events/onboarding/<farm>.json` | `onboarding_profiles` | `scripts/migrate_json_to_db.py` | `TestOnboardingParity` | `PERSISTENCE_BACKEND_ONBOARDING` |
| Loans | *(none - see below)* | `loans` | `scripts/migrate_json_to_db.py` (dataset-embedded loans only) | covered indirectly via migration reconciliation | `PERSISTENCE_BACKEND_LOANS` |
| Users / Farms / Memberships | *(none - always DB, P3-native)* | `users`, `farms`, `farm_memberships` | n/a - created directly by `identity/seed.py` on first touch | `test_farm_isolation.py` | always active |

Setting `PERSISTENCE_BACKEND=db` overrides the default for every domain at
once; `PERSISTENCE_BACKEND_<DOMAIN>` overrides just one. Either can be
rolled back by unsetting/resetting the variable - no code deploy required,
no data is destroyed by flipping the flag back (the JSON files are never
deleted by cutting a domain over to `db`).

### Loans - the one true exception, not a gap

The **canonical sample dataset**'s embedded `loans` array
(`datasets/multi_sector_farm.json`) has always been the sole source for a
dataset-backed demo farm's loans - farmers have never been able to edit
it, and there never was a writable JSON store for loans to migrate away
from. `JsonLoanRepository.load()` therefore intentionally returns `None`
(distinct from `[]`) as an explicit "no DB rows recorded, keep using the
dataset" sentinel. A farm only gets real, farmer-editable loan rows once
`PERSISTENCE_BACKEND_LOANS=db` **and** it has DB rows (from the migration
script, or from `services/loans_service.py` going forward).

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

## Recommended cutover order (not yet executed)

For a real deployment, the safest order - least to most behaviourally
sensitive - is:

1. **Category budgets** - simplest shape, no cross-references to another
   domain, upsert semantics already schema-enforced via the unique
   constraint on `(farm_id, sector, record_type, category, year, month)`.
2. **Financial records** - the `origin_document_id` uniqueness constraint
   is schema-enforced; no other domain's rows reference a financial
   record's id from the JSON side, so cutover is low-risk in isolation.
3. **Documents** - depends on (2) being already cut over first in the
   same environment, since a document's `linked_financial_record_id`
   should point at a DB financial record once documents are DB-backed.
4. **Onboarding** - low risk (one row per farm, no cross-references).
5. **Loans** - only after running `scripts/migrate_json_to_db.py` for the
   farm(s) in question and reconciling loan totals; until then, leave
   `PERSISTENCE_BACKEND_LOANS=json` so dataset-embedded loans keep working.

Before flipping any domain's flag in production: run
`python -m scripts.migrate_json_to_db --farm-file <file> --dry-run`,
review the reconciliation output, re-run with `--apply`, then flip only
that domain's `PERSISTENCE_BACKEND_<DOMAIN>` variable. Take a backup first
(see `docs/backup_and_recovery.md`).

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
