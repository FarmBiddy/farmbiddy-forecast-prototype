"""
Persistence boundary between services and storage (P3.1/P3.4).

Each domain module (`financial_records.py`, `documents.py`,
`category_budgets.py`, `onboarding.py`, `loans.py`) exposes a
`get_repository()` factory returning either a JSON-file-backed or a
database-backed implementation of that domain's repository contract,
selected per `config.settings.backend_for(domain)` (an environment variable,
independently flippable per domain - see the P3 completion report's "dual
path" design).

Every repository speaks in the exact same plain-dict shapes the services
already use - the JSON implementations are close to a direct lift of the
pre-P3 file I/O helpers, and the DB implementations translate to/from the
SQLAlchemy ORM models in `db/orm_models.py`. Business logic (validation,
dedup, upsert rules, aggregation) stays in `services/*.py`, unchanged,
either way - only the load/save primitives move.
"""
