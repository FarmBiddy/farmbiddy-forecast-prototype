# Phase 2: Forecast Backend Unification (Deferred)

Phase 1 merged upload, daily updates, and tests into DAIRY FINANCIALS while keeping `forecast_engine/` as the sole source of dashboard numbers. Phase 2 optionally unifies forecasting on the Financial Intelligence `financial_engine` pipeline.

## Goals

1. Run forecasts through one adapter without breaking Farmer Edition routes.
2. Validate pipeline outputs against `forecast_engine` before switching UI surfaces.
3. Retire duplicate Monte Carlo and rule-only intelligence once numbers match farmer expectations.

## Proposed adapter: `services/forecast_backend.py`

```python
class ForecastBackend(Protocol):
    def run(self, farm: dict, horizon_months: int, **options) -> dict: ...

class SimpleBackend:
    """Wraps existing services.forecast_service.run_forecast."""

class PipelineBackend:
    """Wraps financial_engine via services.pipeline_service.run_pipeline."""
```

Configuration (env or `config/farm_profile.json`):

- `forecast_backend=simple` (default, Phase 1 behaviour)
- `forecast_backend=pipeline` (Phase 2 opt-in)

## Migration order

1. **Forecasts page** — `/farmer/run-advanced-forecast`, `/farmer/run-monte-carlo`
2. **Financial Intelligence** — swap data source; port `farmer_edition_service.py` + `farmer_language.py`
3. **Reports** — feed `report_service.py` from pipeline KPIs (keep 16-page PDF layout)
4. **Legacy API** — `/analyse`, `/sandbox`, `/forecast/*` behind the same adapter

## Dependencies to add when Phase 2 starts

- Copy `financial_engine/` from FI source if not already present
- Add to `requirements.txt`: `scipy`, `statsmodels`, `scikit-learn`
- Port FI tests: `test_pipeline.py`, `test_simulation.py`, `test_statistics_models.py`, etc.

## Validation checklist

- Side-by-side compare revenue, profit, cash balance for all 7 sample farms (± tolerance)
- Scenario sandbox factor changes produce directionally consistent deltas
- PDF report section totals match dashboard after switch
- Full pytest suite green including pipeline tests

## Out of scope until Phase 2 approved

- Replacing DAIRY `report_service.py` with FI `reports/` package
- Server-side authentication or Supabase
- Removing `forecast_engine/` or FI archive folder
