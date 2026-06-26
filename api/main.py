"""
FarmBiddy Financial Forecast Skill — FastAPI application.

Serves the visual web interface at GET / and exposes JSON API routes
under /api/... (legacy root API paths remain for backward compatibility).
"""

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from config.paths import CHARTS_DIR, FRONTEND_DIR, REPORTS_DIR, ensure_output_dirs
from services.forecast_service import (
    FarmFileNotFoundError,
    ForecastFileNotFoundError,
    InvalidFarmDataError,
)

app = FastAPI(
    title="FarmBiddy Farmer Edition",
    description=(
        "Professional dairy farm financial management for farmers. "
        "Open the home page for the Farmer Edition dashboard, or use /api/... "
        "endpoints and /docs for the JSON API."
    ),
    version="1.0.0",
    contact={"name": "FarmBiddy"},
)


# Create writable/output folders before StaticFiles mounts (required on fresh deploy).
ensure_output_dirs()
os.makedirs(FRONTEND_DIR, exist_ok=True)


@app.on_event("startup")
def startup():
    """Re-ensure folders exist after redeploy or storage path changes."""
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
