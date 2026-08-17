# Main FarmBiddy platform integration

This financial service is a **prototype API** the main FarmBiddy platform can
call later. It does **not** authenticate farmers itself.

## Purpose

Collect, organise, compare, forecast and explain farm finances. Farmers use
the bundled UI; the main platform will later call the same `/api/...` routes.

## Architecture

```
Main FarmBiddy Platform
  → authenticates user
  → resolves authorised farm
  → calls this API with identity/farm claims
      → IdentityProvider → RequestIdentity
      → enforce_farm_access (membership + role)
      → farm-scoped services / repositories
      → forecast_engine (calculations)
      → structured JSON response
```

Business services never import login, sessions or passwords. They depend only
on `RequestIdentity` (`identity/context.py`).

## Identity seam

Today: `DevIdentityProvider` (`IDENTITY_PROVIDER=dev`). One seeded development
user; dataset-backed farms are auto-enrolled as `owner`.

Later: add `PlatformIdentityProvider` that implements the same protocol:

```python
class IdentityProvider(Protocol):
    def resolve(self, session: Session) -> RequestIdentity: ...
```

Minimum external context the platform should supply:

| Claim | Maps to |
|---|---|
| External user id | `RequestIdentity.user_id` (and `users.id` if persisted here) |
| Display name | `RequestIdentity.display_name` |
| Authorised farm id(s) | `FarmMembership.farm_id` / `Farm.slug` |
| Role | `owner` \| `manager` \| `advisor` \| `accountant` \| `read_only` |

Do not invent a proprietary auth protocol. A signed JWT or trusted gateway
header from the main platform is enough. Register the new provider in
`identity.context._PROVIDERS` and set `IDENTITY_PROVIDER`. **No financial
service or repository change is required.**

Write roles: `owner`, `manager`. Read-only: `advisor`, `accountant`, `read_only`.

## Farm context

Every mutable request: `farm_file` query/body → resolve farm → membership check
→ service → farm-scoped repository. Never trust a client-supplied farm id
without `enforce_farm_access`.

If the identity has one farm, enter it automatically (prototype default).
Multiple farms: pass `farm_file`.

## Who does what

### Main FarmBiddy platform (intended)

- Real authentication and session/JWT
- User directory / organisation membership in the wider product
- Broader FarmBiddy navigation (this UI is the financial prototype shell)
- Supplying identity + authorised farm + role into this API

This prototype does **not** implement those.

### This financial service

- Financial records (income/expense)
- Documents (invoices/receipts; farmer confirms before Actuals)
- Category budgets and Budget vs Actual
- Cash flow, dashboard overview, profitability, historical comparison
- Forecasting and What If? via `forecast_engine`
- Financial alerts (“Needs Your Attention”)
- Financial reports (including accountant/advisor summary)
- Farm-scoped persistence of the above
- Enforcing farm membership on requests once identity is resolved

### Integration decisions (not settled here)

Do not assign these until the platform wiring is designed:

- Whether farm master data (name, land, herd identifiers) lives only here, only on the platform, or is synced
- Whether `users` / `farm_memberships` in this database remain the access source of truth or become a cache of platform grants
- Billing, notifications, and document file storage vs attachment references
- Who owns processor/dairy-statement credentials when a real provider is added

Until then: this API is the **financial system of record** for money data it stores; the platform is the **identity and product shell**.

## Main endpoints (prefer `/api/...`)

Paths below are relative to `/api`. OpenAPI: `/docs`.

| Domain | READ | WRITE | CALCULATION | EXPORT |
|---|---|---|---|---|
| Farm profile / sectors | `GET /farmer/profile`, `GET /farmer/sectors`, `GET /farmer/onboarding` | Farm Setup `POST /farmer/onboarding` | — | `GET /farmer/farm-data/export` |
| Financial records | `GET /farmer/financial-records` | POST/PUT/DELETE same path | — | export |
| Documents | `GET /farmer/documents` | POST/PUT/DELETE same | paid+confirmed → linked record | export |
| Category budgets | `GET /farmer/category-budgets` | `.../monthly`, `.../annual`, PUT, DELETE | — | export |
| Budget vs Actual | `GET /farmer/category-budget-vs-actual`, `GET /farmer/cashflow-budget` | — | comparison | reports |
| Cash flow / dashboard | `GET /farmer/dashboard`, `POST /farmer/run-analysis` | analysis saves forecast artefacts, not Actuals | `forecast_engine` | reports |
| Loans | dashboard / loans summary on analysis | via onboarding / DB overlay (UI CRUD limited) | debt register | export |
| Forecast / What If? | `POST /farmer/scenario-sandbox`, `GET /farmer/cashflow-actions` | — | yes | What If? report |
| Alerts | analysis `needs_attention` / Action Plan | — | yes | reports |
| Reports | `GET /farmer/report` (preview) | `POST /farmer/report` (PDF) | yes | download |

Legacy: the same router is also mounted **without** `/api` for old clients.
New integrations should use `/api`.

One-page map: `docs/prototype_v1_technical_overview.md`.

## Financial semantics

- **Actual** — dataset months up to `dataset_coverage_cutoff`, plus
  FinancialRecords and paid+confirmed document-linked records after that
  cutoff. Never double-count.
- **Budget** — farmer category plans. Missing budget → `no_budget_set`, not zero.
- **Forecast** — engine projection from assumptions + history. Not an Actual.
- **Scenario / What If?** — same engine with overridden inputs. Not persisted
  as Actuals.

Money is EUR, two decimal places. Dates are ISO. Percentages are 0–100 in
farmer-facing copy unless a field is clearly a 0–1 fraction.

## Data ownership

**This service stores:** farms, memberships, financial records, documents,
category budgets, onboarding/farm configuration, loans (when first-class),
generated reports/charts under `STORAGE_PATH`.

**The main platform may later own:** user login, organisation, billing,
notifications. It should treat this API as the financial system of record
for farm money data.

The canonical `datasets/*.json` files are **sample/reference**, not farmer
Actuals.

## Error handling

| HTTP | Meaning |
|---|---|
| 400 | Validation / bad input (`detail` string) |
| 403 | No membership or read-only role on a write |
| 404 | Farm or record not found |
| 422 | Schema validation (Pydantic) |
| 500 | Unexpected server error |

Do not retry writes blindly; financial creates are not always idempotent
except where a unique `origin_document_id` / provider reference exists.

## Future integrations (not in this prototype)

Document providers (`services/document_providers.py`) are the boundary for
OCR, email, bank feeds and accounting imports. They propose documents; the
farmer confirms before Actuals change. Do not add fake production
integrations here.
