"""
FarmBiddy API routes — shared by /api/... and legacy root paths.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.api_models import (
    AnalyseRequest,
    AnalyseResponse,
    ApplicationStatus,
    BenchmarkRequest,
    BenchmarkResponse,
    ChartGenerationRequest,
    ChartGenerationResponse,
    ChartListResponse,
    ComparisonRequest,
    ComparisonResponse,
    ErrorResponse,
    FarmListResponse,
    FarmSummary,
    ForecastHistoryResponse,
    ForecastRequest,
    ForecastResponse,
    SandboxRequest,
    SandboxResponse,
)
from services.chart_service import get_chart_info, list_chart_files
from services.comparison_service import benchmark_forecasts, compare_forecasts, list_forecast_history
from services.forecast_service import (
    list_available_farms,
    run_chart_generation,
    run_forecast,
    run_multi_farm_analysis,
    run_sandbox_forecast,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@router.get(
    "/status",
    response_model=ApplicationStatus,
    tags=["System"],
    summary="Application status (JSON)",
)
def application_status():
    return ApplicationStatus(
        application="FarmBiddy Financial Forecast Skill",
        version="prototype",
        status="running",
    )


# ---------------------------------------------------------------------------
# Farms
# ---------------------------------------------------------------------------

@router.get(
    "/farms",
    response_model=FarmListResponse,
    tags=["Farms"],
    summary="List available farms",
)
def get_farms():
    farms_data = list_available_farms()
    farms = [FarmSummary(**farm) for farm in farms_data]
    return FarmListResponse(farms=farms, count=len(farms))


# ---------------------------------------------------------------------------
# Visual interface — multi-farm analysis
# ---------------------------------------------------------------------------

@router.post(
    "/analyse",
    response_model=AnalyseResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["Analysis"],
    summary="Run analysis for one or more farms",
    description=(
        "Primary endpoint for the visual web interface. "
        "Runs forecasts for selected farms and returns either a single-farm "
        "dashboard or a multi-farm comparison table."
    ),
)
def analyse_farms(request: AnalyseRequest):
    try:
        result = run_multi_farm_analysis(
            farm_files=request.farm_files,
            outputs=request.outputs,
            chart_types=request.chart_types,
            save_result=request.save_result,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return AnalyseResponse(**result)


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

@router.post(
    "/forecast",
    response_model=ForecastResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    tags=["Forecast"],
    summary="Run a selective forecast",
)
def create_forecast(request: ForecastRequest):
    result = run_forecast(
        farm_file=request.farm_file,
        outputs=request.outputs,
        save_result=request.save_result,
        generate_charts=request.generate_charts,
    )
    return ForecastResponse(**result)


@router.get(
    "/forecast/history",
    response_model=ForecastHistoryResponse,
    responses={400: {"model": ErrorResponse}},
    tags=["Forecast"],
    summary="List historical forecasts",
)
def get_forecast_history(
    sort_by: Optional[str] = Query(
        default="generated_at",
        description="Sort field: annual_profit, generated_at, or risk_level",
    ),
):
    try:
        history = list_forecast_history(sort_by=sort_by)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ForecastHistoryResponse(**history)


@router.post(
    "/forecast/compare",
    response_model=ComparisonResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["Forecast"],
    summary="Compare selected forecasts",
)
def compare_forecast_runs(request: ComparisonRequest):
    try:
        result = compare_forecasts(
            forecast_files=request.forecast_files,
            compare_all=request.compare_all,
            metrics=request.metrics,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ComparisonResponse(**result)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

@router.post(
    "/forecast/charts",
    response_model=ChartGenerationResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["Charts"],
    summary="Generate forecast charts",
)
def generate_charts(request: ChartGenerationRequest):
    try:
        result = run_chart_generation(
            farm_file=request.farm_file,
            chart_types=request.charts,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ChartGenerationResponse(**result)


@router.get(
    "/charts",
    response_model=ChartListResponse,
    tags=["Charts"],
    summary="List available charts",
)
def get_charts():
    charts = list_chart_files()
    return ChartListResponse(charts=charts, count=len(charts))


@router.get(
    "/charts/{chart_name}",
    responses={404: {"model": ErrorResponse}},
    tags=["Charts"],
    summary="Get chart information",
)
def get_chart(chart_name: str):
    try:
        return get_chart_info(chart_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/chart/{chart_name}",
    responses={404: {"model": ErrorResponse}},
    tags=["Charts"],
    summary="Get chart information (alias)",
    include_in_schema=True,
)
def get_chart_alias(chart_name: str):
    """Alias used by the visual web interface."""
    return get_chart(chart_name)


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

@router.post(
    "/sandbox",
    response_model=SandboxResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    tags=["Sandbox"],
    summary="Run advisor sandbox forecast",
)
def run_sandbox(request: SandboxRequest):
    try:
        result = run_sandbox_forecast(
            farm_file=request.farm_file,
            changes=request.changes,
            outputs=request.outputs,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return SandboxResponse(**result)


# ---------------------------------------------------------------------------
# Benchmarking
# ---------------------------------------------------------------------------

@router.post(
    "/benchmark",
    response_model=BenchmarkResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["Benchmarking"],
    summary="Benchmark forecast performance",
)
def run_benchmark(request: BenchmarkRequest):
    try:
        result = benchmark_forecasts(
            forecast_files=request.forecast_files,
            compare_all=request.compare_all,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return BenchmarkResponse(**result)
