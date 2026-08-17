# FarmBiddy Financial Prototype v1 — product audit

Status key: **COMPLETE** (in this prototype) · **PARTIAL** (present with
limits) · **FUTURE** (explicitly out of scope for v1).

| Requirement | Status | Evidence | Known limitation |
|---|---|---|---|
| Finances in one place | COMPLETE | Overview, Cash Flow, Farm Data, reports share farm-scoped services | Demo still mixes sample dataset history with farmer-owned DB rows (by design, `dataset_coverage_cutoff`) |
| Income/expense tracking | COMPLETE | FinancialRecords API + Income/Expenses UI | Categories are a fixed vocabulary |
| Invoice/receipt workflow | COMPLETE | Documents → review → paid+confirmed → linked record; duplicate prevention | No OCR; manual entry / provider boundary only |
| Automatic organisation architecture | PARTIAL | Category aggregation, document→record link, provider protocol | Real automatic capture is FUTURE |
| Cash-flow monitoring | COMPLETE | Cash Flow view, lowest-cash, alerts | Engine remains somewhat dairy-oriented for some assumptions |
| Forward forecast | COMPLETE | `forecast_engine` → dashboard / What If? / reports | Not a generic multi-sector rewrite |
| Budget vs Actual | COMPLETE | Category budgets distinct from Actuals; `no_budget_set` not zero | Dataset cash-flow budget is separate from category budgets |
| Profitability | COMPLETE | Overview KPIs, Farm Performance | Sample margins are illustrative |
| Historical comparison | COMPLETE | Previous Years / YoY with like-for-like months | Partial years explained in plain language |
| Debt/loans | COMPLETE | Dataset/DB overlay, Loans & Finance, alerts | Farmer cannot fully CRUD loans in UI yet |
| What If? | COMPLETE | Presets + sandbox, farmer-facing outcomes | Advanced engine detail behind progressive disclosure |
| Alerts / Needs Your Attention | COMPLETE | Action Plan from existing alert services | Wording still conservative; no AI recommendations |
| Accountant/advisor reporting | COMPLETE | Report types including advisor summary | Not a statutory accounts pack |
| Multi-sector behaviour | PARTIAL | Dairy/beef/lamb selection; dairy-only What If? hidden when not selected | Suckler/tillage/other are labelled in onboarding more than in the engine |
| Farm isolation | COMPLETE | Membership + `enforce_farm_access`; `tests/test_farm_isolation.py` | Prototype uses a dev identity adapter |
| API integration readiness | COMPLETE | `IdentityProvider` seam; `docs/main_platform_integration.md`; OpenAPI `/docs` | No live platform JWT yet |
| Persistence | COMPLETE | SQLAlchemy/Alembic; DB default; JSON rollback; migration script | Cutover of existing JSON files is an operator step |
| Farmer-first UX | COMPLETE | Collect→Organise→Understand→Compare→Forecast→Act; SAMPLE badge; plain-language errors | Tablet/desktop primary; mobile usable not native |
| OCR | FUTURE | Provider protocol only | No real provider |
| Bank/accounting feeds | FUTURE | Same provider boundary | Not implemented |
| Biddy/AI | FUTURE | — | Not implemented |
| External benchmarking | FUTURE | Placeholder route tagged as such | Not live data |
| Standalone login | FUTURE | Deferred to main FarmBiddy platform | `DevIdentityProvider` only |
