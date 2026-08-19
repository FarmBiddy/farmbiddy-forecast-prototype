"""
FarmBiddy Financial Forecast Skill — FastAPI application.

Serves the visual web interface at GET / and exposes JSON API routes
under /api/... (legacy root API paths remain for backward compatibility).
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

# Headless hosts (Render): pin Agg and a writable cache *before* any later
# matplotlib import. Font discovery against a missing/read-only home can
# block Uvicorn from binding $PORT.
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault(
    "MPLCONFIGDIR",
    os.path.join(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp", "farmbiddy-mpl"),
)

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from api.capabilities_routes import router as capabilities_router
from config.paths import CHARTS_DIR, FRONTEND_DIR, REPORTS_DIR, ensure_output_dirs
from identity.access import FarmAccessDeniedError
from services.forecast_service import (
    FarmFileNotFoundError,
    ForecastFileNotFoundError,
    InvalidFarmDataError,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Required bootstrap only — Uvicorn binds the listen port *after* this
    completes. Keep it short: directories, SQLite schema, optional demo rows.
    """
    ensure_output_dirs()
    os.makedirs(FRONTEND_DIR, exist_ok=True)
    os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
    from config.settings import IS_SQLITE
    from db.session import init_db
    from scripts.seed_demo_farm import maybe_seed_on_startup

    if IS_SQLITE and "pytest" not in sys.modules:
        init_db()
    maybe_seed_on_startup()
    yield


app = FastAPI(
    title="FarmBiddy Financial Platform API",
    description=(
        "Farmer-facing financial management and forecasting for FarmBiddy.\n\n"
        "**Money** is euro (€), stored to 2 decimal places. **Dates** are ISO "
        "`YYYY-MM-DD`. **Periods** are calendar months unless a response names "
        "a trailing-12-month window.\n\n"
        "**Actual** = recorded income/expense (dataset history after "
        "`dataset_coverage_cutoff`, plus farmer FinancialRecords and "
        "paid+confirmed documents). **Budget** = farmer-set category plans. "
        "**Forecast** = `forecast_engine` projection. These three are never merged "
        "into one number.\n\n"
        "**Farm scope:** pass `farm_file` (legacy farm identifier). Access is "
        "checked against the request identity's farm membership. In this "
        "standalone prototype the identity is a development adapter; the main "
        "FarmBiddy platform will later supply authenticated user/farm claims "
        "through the same `IdentityProvider` seam — see "
        "`docs/main_platform_integration.md`.\n\n"
        "Routes are mounted at `/api/...`. The same router is also mounted at "
        "the root for legacy clients; prefer `/api/` for new integrations."
    ),
    version="1.0.0",
    contact={"name": "FarmBiddy"},
    lifespan=lifespan,
    openapi_tags=[
        {"name": "System", "description": "Health and application status."},
        {"name": "Farmer Edition", "description": "Farm-scoped farmer workflows: records, documents, budgets, dashboard, What If?, reports."},
        {"name": "Farms", "description": "Farm listing and selection."},
        {"name": "Analysis", "description": "Run analysis that populates dashboard views."},
        {"name": "Forecast", "description": "Forecast generation (CALCULATION). Does not persist farmer Actuals."},
        {"name": "Charts", "description": "Generated chart artefacts."},
        {"name": "Sandbox", "description": "What If? scenario calculations."},
        {"name": "Benchmarking", "description": "Placeholder benchmark endpoint — not a live external comparison."},
    ],
)


# Create writable/output folders before StaticFiles mounts (required on fresh deploy).
ensure_output_dirs()
os.makedirs(FRONTEND_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(FarmFileNotFoundError)
async def farm_not_found_handler(_request, exc: FarmFileNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ForecastFileNotFoundError)
async def forecast_not_found_handler(_request, exc: ForecastFileNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(_request, exc: FileNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(InvalidFarmDataError)
async def invalid_farm_handler(_request, exc: InvalidFarmDataError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(FarmAccessDeniedError)
async def farm_access_denied_handler(_request, exc: FarmAccessDeniedError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception):
    logging.getLogger("farmbiddy").exception("Unhandled API error")
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again in a moment."},
    )


# ---------------------------------------------------------------------------
# Static files — CSS, JS, and generated Plotly chart HTML
# ---------------------------------------------------------------------------

app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
app.mount("/chart-files", StaticFiles(directory=CHARTS_DIR), name="chart_files")
app.mount("/report-files", StaticFiles(directory=REPORTS_DIR), name="report_files")


# ---------------------------------------------------------------------------
# Visual interface home page
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def serve_frontend():
    """Serve the visual demo interface instead of raw JSON."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    return FileResponse(index_path)


# ---------------------------------------------------------------------------
# API routes — /api/... plus legacy root paths (unchanged for Swagger/clients)
# ---------------------------------------------------------------------------

app.include_router(api_router, prefix="/api")
app.include_router(api_router)
app.include_router(capabilities_router, prefix="/api")
