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
    FarmerProfileResponse,
    FarmerDashboardResponse,
    FarmerAnalysisResponse,
    FarmerAdvancedForecastResponse,
    FarmerMonteCarloRequest,
    FarmerMonteCarloResponse,
    FarmerRunAnalysisRequest,
    ScenarioSandboxRequest,
    ScenarioSandboxResponse,
    FinancialIntelligenceResponse,
    AskAdvisorRequest,
    AskAdvisorResponse,
    FarmerReportRequest,
    FarmerReportResponse,
    FarmerReportPreviewResponse,
    SectorListResponse,
)
from services.chart_service import get_chart_info, list_chart_files
from services.comparison_service import benchmark_forecasts, compare_forecasts, list_forecast_history
from services.financial_intelligence_service import ask_farm_advisor, get_financial_intelligence
from services.report_service import generate_farmer_report, get_report_preview
from services.farmer_dashboard_service import (
    get_farmer_dashboard_preview,
    get_farmer_profile,
    get_sectors_list,
    list_farms_for_selector,
    run_advanced_forecast,
    run_farmer_analysis,
    run_monte_carlo_for_farm,
    resolve_farm_file,
)
from services.scenario_sandbox_service import run_scenario_sandbox
from services.forecast_service import (
    list_available_farms,
    run_chart_generation,
    run_forecast,
    run_multi_farm_analysis,
    run_sandbox_forecast,
)

router = APIRouter()


def _parse_sectors_query(sectors: Optional[str] = None) -> Optional[list[str]]:
    if not sectors:
        return None
    return [part.strip() for part in sectors.split(",") if part.strip()]


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
        application="FarmBiddy Farmer Edition",
        version="1.0.0",
        status="running",
    )


# ---------------------------------------------------------------------------
# Farmer Edition
# ---------------------------------------------------------------------------

@router.get(
    "/farmer/profile",
    response_model=FarmerProfileResponse,
    tags=["Farmer Edition"],
    summary="Active farm profile",
)
def farmer_profile(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    return FarmerProfileResponse(**get_farmer_profile(farm_id, _parse_sectors_query(sectors)))


@router.get(
    "/farmer/sectors",
    response_model=SectorListResponse,
    tags=["Farmer Edition"],
    summary="List available farm sectors",
)
def farmer_sectors(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    payload = get_sectors_list(farm_id, _parse_sectors_query(sectors))
    return SectorListResponse(success=True, **payload)


@router.get(
    "/farmer/dashboard",
    response_model=FarmerDashboardResponse,
    tags=["Farmer Edition"],
    summary="Dashboard preview with fallback KPIs",
)
def farmer_dashboard(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    data = get_farmer_dashboard_preview(farm_id, _parse_sectors_query(sectors))
    return FarmerDashboardResponse(**data)


@router.post(
    "/farmer/run-analysis",
    response_model=FarmerAnalysisResponse,
    tags=["Farmer Edition"],
    summary="Run forecast and populate farmer dashboard",
)
def farmer_run_analysis(request: FarmerRunAnalysisRequest = FarmerRunAnalysisRequest()):
    try:
        return FarmerAnalysisResponse(**run_farmer_analysis(
            request.farm_file,
            save_result=True,
            sectors=request.sectors,
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/run-advanced-forecast",
    response_model=FarmerAdvancedForecastResponse,
    tags=["Farmer Edition"],
    summary="Run advanced forecast with Monte Carlo and scenarios",
)
def farmer_advanced_forecast(request: FarmerRunAnalysisRequest = FarmerRunAnalysisRequest()):
    try:
        return FarmerAdvancedForecastResponse(**run_advanced_forecast(
            request.farm_file,
            sectors=request.sectors,
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/run-monte-carlo",
    response_model=FarmerMonteCarloResponse,
    tags=["Farmer Edition"],
    summary="Run Monte Carlo simulation",
)
def farmer_monte_carlo(request: FarmerMonteCarloRequest):
    try:
        return FarmerMonteCarloResponse(**run_monte_carlo_for_farm(
            request.farm_file,
            request.iterations,
            sectors=request.sectors,
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/farmer/scenario-sandbox",
    response_model=ScenarioSandboxResponse,
    tags=["Farmer Edition"],
    summary="Compare base case vs scenario assumptions",
)
def farmer_scenario_sandbox(request: ScenarioSandboxRequest):
    try:
        farm_file = resolve_farm_file(request.farm_file)
        payload = run_scenario_sandbox(farm_file, request.model_dump())
        return ScenarioSandboxResponse(**payload)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get(
    "/farm-profile",
    response_model=FarmerProfileResponse,
    tags=["Farmer Edition"],
    summary="Alias for active farm profile",
    include_in_schema=True,
)
def farm_profile_alias(farm_id: Optional[str] = Query(default=None, alias="farm_file")):
    return FarmerProfileResponse(**get_farmer_profile(farm_id))


@router.get(
    "/farmer/financial-intelligence",
    response_model=FinancialIntelligenceResponse,
    tags=["Farmer Edition"],
    summary="Financial intelligence for the selected farm",
)
def farmer_financial_intelligence(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        return FinancialIntelligenceResponse(**get_financial_intelligence(
            farm_id,
            sectors=_parse_sectors_query(sectors),
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/ask-advisor",
    response_model=AskAdvisorResponse,
    tags=["Farmer Edition"],
    summary="Ask the rule-based farm advisor",
)
def farmer_ask_advisor(request: AskAdvisorRequest):
    try:
        return AskAdvisorResponse(**ask_farm_advisor(
            request.question,
            request.farm_file,
            sectors=request.sectors,
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/farmer/report",
    response_model=FarmerReportPreviewResponse,
    tags=["Farmer Edition"],
    summary="Preview report content before PDF generation",
)
def farmer_report_preview(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    report_type: str = Query(default="full"),
    report_date: Optional[str] = Query(default=None),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        return FarmerReportPreviewResponse(**get_report_preview(
            farm_id,
            report_type,
            report_date,
            sectors=_parse_sectors_query(sectors),
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/report",
    response_model=FarmerReportResponse,
    tags=["Farmer Edition"],
    summary="Generate a professional PDF farm report",
)
def farmer_generate_report(request: FarmerReportRequest):
    try:
        return FarmerReportResponse(**generate_farmer_report(
            request.farm_file,
            request.report_type,
            request.report_date,
            sectors=request.sectors,
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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
