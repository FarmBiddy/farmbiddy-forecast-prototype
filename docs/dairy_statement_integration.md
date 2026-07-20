# Dairy Statement Integration

## 1. Purpose

This is a **mocked** dairy statement integration for development. It exists so the
FarmBiddy financial engine can be built and tested against a realistic, normalised
dairy co-op statement shape *before* a real document-management service exists.

Nothing here talks to a real dairy processor, a database, or the network. The
"provider" in this integration is a hardcoded, in-memory implementation that
returns one fixed sample statement (from a reference document) for a single
provider ID, `STRATHROY`.

## 2. Current flow

```
MockDairyStatementProvider
    -> DairyStatementResponse (normalised contract)
    -> dairy statement adapter
    -> existing monthly-entry structure (services/multi_sector_farm.py)
    -> existing FarmBiddy financial engine (forecast_engine/)
```

Nothing in `forecast_engine/`, `financial_engine/`, `services/multi_sector_farm.py`,
the API routes, or the frontend was changed to build this. The adapter's output is
a plain dict shaped like an existing dairy monthly entry — the rest of the system
consumes it exactly as it already consumes any other monthly entry.

## 3. Future flow

The mock provider is the only piece of this design meant to be temporary. The
intended replacement path is:

```
Document-management service
    -> RAG / Supabase (document storage and retrieval — not part of this integration)
    -> real dairy statement provider (e.g. an HTTP-backed implementation)
    -> same normalised contract (DairyStatementResponse)
    -> same adapter
    -> financial engine
```

Everything from the normalised contract onward is designed to stay unchanged when
the mock is replaced. See section 8 for how that replacement works in practice.

## 4. Responsibilities

This integration handles:

- Receiving a normalised dairy statement (currently from a mock, in future from a
  real provider).
- Validating that statement against a strict, typed contract.
- Adapting it into the shape the existing financial engine already understands.

This integration does **not** handle:

- Document uploads.
- PDF parsing.
- OCR.
- RAG (retrieval-augmented generation).
- Supabase or any other persistence layer.
- Authentication.
- The final external provider API (no real HTTP calls are made anywhere in this
  integration).

## 5. Normalised JSON contract

Example based on the reference document's Strathroy sample:

```json
{
  "success": true,
  "provider": { "id": "STRATHROY", "name": "Strathroy Dairy" },
  "statement": {
    "statement_id": "66518",
    "period": { "month": 2, "year": 2026 },
    "payment_date": null
  },
  "supplier": { "supplier_no": "152", "farmer_name": "John Doe Farms Ltd" },
  "collections": { "collection_count": 15, "total_litres": 38804 },
  "quality": {
    "butterfat_percent": "4.43",
    "protein_percent": "3.14",
    "lactose_percent": "4.62",
    "scc": 249,
    "tbc": 10
  },
  "pricing": {
    "base_price_ppl": "33.49",
    "gross_price_ppl": "37.419",
    "vat_percent": "4.5",
    "total_payment": "14476.66",
    "currency": "EUR"
  }
}
```

Defined in `models/dairy_statement.py` as `DairyStatementResponse`, using
`decimal.Decimal` for every numeric field that represents money, a rate, or a
percentage (never `float`), to avoid floating-point precision loss.

## 6. Field mapping

| Statement field | Adapter output | Notes |
|---|---|---|
| `supplier.supplier_no` | *(not carried into the monthly entry)* | Available on the source statement for traceability; not part of the legacy monthly-entry shape. |
| `statement.statement_id` | `_source_statement.statement_id` | Traceability only — not read by the forecast engine. |
| `collections.total_litres` | `operational.milk_litres` | Direct copy, cast to `float`. |
| `quality.butterfat_percent` | `quality.butterfat_percent` | Copied through unchanged; not consumed by any existing calculation today. |
| `quality.protein_percent` | `quality.protein_percent` | Same as above. |
| `quality.lactose_percent` | `quality.lactose_percent` | Same as above. |
| `quality.scc` | `quality.scc` | Same as above. |
| `quality.tbc` | `quality.tbc` | Same as above. |
| `pricing.base_price_ppl` | *(not carried into the monthly entry)* | Kept on the source statement as reference data only. Never used to derive the engine's effective price. |
| `pricing.gross_price_ppl` | `pricing.milk_price_per_litre` | **This is the effective price field.** Converted from pence-per-litre to currency-per-litre (see section 7). |
| `pricing.vat_percent` | *(not carried into the monthly entry)* | Available on the source statement; not consumed by the legacy engine, which has no VAT concept. |
| `pricing.total_payment` | `revenue.milk` and `revenue.total` | **This is the authoritative payment.** Used directly, never recomputed from litres x price, and never double-counted against a derived figure. |

Not populated in the adapter output, and deliberately so: `operational.milking_cows`,
`operational.calves`, `operational.dry_cows`, and the entire `costs` breakdown
(`feed`, `vet`, `labour`, etc.). A milk statement contains none of that data — these
fields are left out rather than defaulted to `0` or invented, so the gap stays
visible rather than silently hidden.

## 7. Units

| Field | Unit |
|---|---|
| `collections.total_litres` / `operational.milk_litres` | Litres |
| `quality.butterfat_percent` / `protein_percent` / `lactose_percent` | Percent (e.g. `4.43` means 4.43%) |
| `quality.scc` | Cells per millilitre (somatic cell count) |
| `quality.tbc` | Colony-forming units (total bacterial count) |
| `pricing.base_price_ppl` / `gross_price_ppl` | Pence per litre, exactly as supplied by the provider |
| `pricing.milk_price_per_litre` (adapter output) | Currency major unit per litre (e.g. EUR per litre) |
| `pricing.total_payment` | Currency major unit (e.g. EUR), total for the statement period |

**Unit conversion** happens in exactly one place: `services/dairy_statement_adapter.py`,
converting `gross_price_ppl` (pence per litre) into currency-per-litre by dividing by
100. No other module in this integration performs unit conversion.

### Financial consistency worked example

Using the reference sample:

- Total litres: `38,804`
- Gross price: `37.419` pence per litre
- Converted gross price: `37.419 / 100 = 0.37419` EUR per litre
- Total payment (from the statement): `14,476.66` EUR

Rate-derived amount: `38,804 x 0.37419 = 14,520.06876` EUR.

That is **43.40876 EUR more** than the actual `total_payment` of `14,476.66` EUR. This
gap is expected, not an error — real dairy statements routinely include VAT, quality
bonuses, deductions, levies, corrections, or rounding that a simple litres x rate
calculation cannot reproduce. Because of this:

- `gross_price_ppl` is treated as the **effective price input** — the best available
  per-litre rate for the period.
- `total_payment` is treated as the **authoritative payment** — the actual amount
  the statement says was paid.
- The adapter preserves both values **independently**. It never overwrites, forces,
  or reconciles one against the other, and `revenue.milk` is always set from
  `total_payment`, never recomputed from litres x price.

## 8. Replacement strategy

`services/dairy_statement_provider.py` defines a `DairyStatementProvider` protocol
with one method, `get_milk_statement(...)`, that returns a `DairyStatementResponse`.
`MockDairyStatementProvider` is one implementation of that protocol.

A future real implementation — such as `HttpDairyStatementProvider`
(`services/http_dairy_statement_provider.py`), which calls a real
document-management service — only needs to implement the same method
signature and return the same validated `DairyStatementResponse`. It can
replace `MockDairyStatementProvider` directly:

- `services/dairy_statement_adapter.py` never imports or references
  `MockDairyStatementProvider` by name — it only depends on the
  `DairyStatementResponse` model.
- The financial engine (`forecast_engine/`, `services/multi_sector_farm.py`) never
  imports anything from the dairy-statement integration at all.

Swapping the provider is therefore a one-file change (implement the new provider
class, register it in the factory below) with no changes required to the adapter
or the financial engine.

## 9. Provider selection

`services/dairy_statement_provider_factory.py` provides
`get_dairy_statement_provider(provider_id)`, the single place that decides which
concrete provider implementation to construct for a given `provider_id`. Callers
are expected to use this factory rather than importing a concrete provider class
directly, so a provider ID can be re-pointed to a different implementation with a
one-line change in the factory's routing table — no caller needs to change.

**Current mock mode.** Today, every registered provider ID resolves to
`MockDairyStatementProvider`. The factory's routing table is built directly from
that class's own `SUPPORTED_PROVIDER_NAMES`, so there is exactly one place
(`services/mock_dairy_statement_provider.py`) that lists which provider IDs are
known. Provider-ID matching in the factory is exact and case-sensitive after
stripping surrounding whitespace — `"STRATHROY"` resolves to the mock
implementation, `"strathroy"` does not — intentionally matching the strict,
case-sensitive `provider_id` validation performed inside `get_milk_statement`
itself, so a provider ID is either valid at both stages or rejected at both,
never accepted at one and rejected at the other.

**Future HTTP provider replacement point.** `services/http_dairy_statement_provider.py`
defines `HttpDairyStatementProvider`, a non-functional skeleton implementing the
same protocol. It accepts an `HttpDairyStatementProviderConfig` (`base_url`,
`api_key`, both blank/`None` by default — no real URL or credential is embedded
anywhere in this repository) and documents the intended future request/response
flow in its docstring. Calling `get_milk_statement` on it always raises
`DairyStatementProviderNotConfiguredError` — it makes no network call and imports
no HTTP client library. It is not registered in the factory; wiring it in for a
real provider ID is a deliberate future step, not something that happens
automatically.

**Required future configuration.** `.env.example` documents three placeholder
variables — `DAIRY_STATEMENT_PROVIDER_MODE`, `DAIRY_STATEMENT_API_BASE_URL`,
`DAIRY_STATEMENT_API_KEY` — for whenever a real provider is wired in. **No code
in this repository currently reads any of them.** They are commented out and are
not required for the current mock flow to run.

**No external integration is active.** As of this phase, nothing in the
dairy-statement integration makes a real HTTP request, reads a real credential,
or talks to any external service. The only working provider is the mock.

## 10. Application service

`services/dairy_statement_service.py` provides `process_dairy_statement(...)`, the
single, stable internal entry point that orchestrates the full flow end to end:
provider selection (`get_dairy_statement_provider`) → statement retrieval
(`provider.get_milk_statement`) → the adapter
(`adapt_dairy_statement_to_monthly_entry`). It is the intended call site for a
future API route, document-management integration, background ingestion process,
or internal financial-analysis workflow — none of which exist yet. It performs no
persistence and no network call itself, and (like every other part of this
integration) it never imports or instantiates `HttpDairyStatementProvider`.

**Inputs:** `provider_id`, `supplier_no`, `invoice_id`, `month_no`, `year` — the
same five values `DairyStatementProvider.get_milk_statement` already takes.

**Result:** a frozen `ProcessedDairyStatement` dataclass with two fields —
`statement` (the untouched, validated `DairyStatementResponse`) and
`monthly_entry` (the adapter's own dict output, unchanged). No second
monthly-entry schema is defined; no value is recalculated between retrieval and
return.

**Testability:** an optional keyword-only `provider_factory` parameter (defaulting
to `get_dairy_statement_provider`) lets tests substitute a fake provider without
a dependency-injection framework — a plain default argument is enough.

Example internal usage:

```python
from services.dairy_statement_service import process_dairy_statement

result = process_dairy_statement(
    provider_id="STRATHROY",
    supplier_no="152",
    invoice_id="66518",
    month_no=2,
    year=2026,
)

result.statement       # validated DairyStatementResponse
result.monthly_entry   # adapter's monthly-entry dict
```

## 11. Current limitations

- Only `STRATHROY` is mocked. Any other `provider_id` raises
  `UnsupportedDairyProviderError`.
- `HttpDairyStatementProvider` exists only as a non-functional skeleton — calling
  it always raises `DairyStatementProviderNotConfiguredError`. It is not wired
  into the provider factory.
- All returned statement values are static sample data from the reference document
  — the mock does not vary its output based on input beyond `provider_id`,
  `supplier_no`, `invoice_id`, `month_no`, and `year`.
- There is no HTTP endpoint exposing this integration. It is only reachable from
  Python code within this repository.
- No external connectivity of any kind — no network calls, no real provider API.
- No document ingestion functionality (no PDF parsing, no OCR, no RAG).
- No database persistence — nothing produced by this integration is saved anywhere.
- A statement's `costs` and herd-count fields (`milking_cows`, `calves`, `dry_cows`)
  cannot be populated from a milk statement alone; see section 6.
- Only `EUR`-denominated statements are supported by the adapter today.
