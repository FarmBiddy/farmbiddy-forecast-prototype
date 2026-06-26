"""
FarmBiddy API routes — shared by /api/... and legacy root paths.
"""

from typing import Optional
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

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
)
from services.chart_service import get_chart_info, list_chart_files
from services.comparison_service import benchmark_forecasts, compare_forecasts, list_forecast_history
from services.financial_intelligence_service import ask_farm_advisor, get_financial_intelligence
from services.report_service import generate_farmer_report, get_report_preview
from services.farmer_dashboard_service import (
    get_farmer_dashboard_preview,
    get_farmer_profile,
    list_farms_for_selector,
    run_advanced_forecast,
    run_farmer_analysis,
    run_monte_carlo_for_farm,
    resolve_farm_file,
)
from services.scenario_sandbox_service import run_scenario_sandbox
from config.paths import RAW_UPLOADS_DIR, ensure_output_dirs
from models.farm_update import ApplyFarmUpdateRequest, ApplyFarmUpdateResponse, DailyUpdateRequest, DailyUpdateResponse, FarmUpdatePreviewResponse
from models.uploaded_financials import UploadResponse
from services.daily_updates_service import apply_daily_updates, list_daily_update_categories
from services.farm_update_service import apply_farm_update, build_upload_preview
from services.file_ingestion_service import ALLOWED_EXTENSIONS, FileIngestionService
from services.forecast_service import (
    InvalidFarmDataError,
    list_available_farms,
    run_chart_generation,
    run_forecast,
    run_multi_farm_analysis,
    run_sandbox_forecast,
)

router = APIRouter()
ingestion_service = FileIngestionService()


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
def farmer_profile(farm_id: Optional[str] = Query(default=None, alias="farm_file")):
    return FarmerProfileResponse(**get_farmer_profile(farm_id))


@router.get(
    "/farmer/dashboard",
    response_model=FarmerDashboardResponse,
    tags=["Farmer Edition"],
    summary="Dashboard preview with fallback KPIs",
)
def farmer_dashboard(farm_id: Optional[str] = Query(default=None, alias="farm_file")):
    data = get_farmer_dashboard_preview(farm_id)
    return FarmerDashboardResponse(**data)


@router.post(
    "/farmer/run-analysis",
    response_model=FarmerAnalysisResponse,
    tags=["Farmer Edition"],
    summary="Run forecast and populate farmer dashboard",
)
def farmer_run_analysis(request: FarmerRunAnalysisRequest = FarmerRunAnalysisRequest()):
    try:
        return FarmerAnalysisResponse(**run_farmer_analysis(request.farm_file, save_result=True))
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
        return FarmerAdvancedForecastResponse(**run_advanced_forecast(request.farm_file))
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
        return FarmerMonteCarloResponse(**run_monte_carlo_for_farm(request.farm_file, request.iterations))
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
):
    try:
        return FinancialIntelligenceResponse(**get_financial_intelligence(farm_id))
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
        return AskAdvisorResponse(**ask_farm_advisor(request.question, request.farm_file))
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
):
    try:
        return FarmerReportPreviewResponse(**get_report_preview(farm_id, report_type, report_date))
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
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/upload",
    response_model=UploadResponse,
    tags=["Upload"],
    summary="Upload and parse a financial file",
)
async def upload_financial_file(file: UploadFile = File(...)):
    ensure_output_dirs()
    original_name = file.filename or "uploaded_file"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    saved_path = Path(RAW_UPLOADS_DIR) / safe_name
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    saved_path.write_bytes(content)
    try:
        parsed = ingestion_service.ingest_file(saved_path, filename=original_name)
    except ValueError as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {error}") from error
    return UploadResponse(
        success=True,
        filename=parsed.filename,
        detected_fields=parsed.detected_fields,
        warnings=parsed.warnings,
        ready_for_forecast=parsed.ready_for_forecast,
    )


@router.post(
    "/upload/preview",
    response_model=FarmUpdatePreviewResponse,
    tags=["Upload"],
    summary="Upload a file and preview profile changes",
)
async def upload_preview(
    file: UploadFile = File(...),
    farm_file: Optional[str] = Form(default=None),
):
    ensure_output_dirs()
    original_name = file.filename or "uploaded_file"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    upload_id = uuid.uuid4().hex
    saved_path = Path(RAW_UPLOADS_DIR) / f"{upload_id}{suffix}"
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    saved_path.write_bytes(content)
    try:
        parsed = ingestion_service.ingest_file(saved_path, filename=original_name)
        return build_upload_preview(upload_id, parsed, farm_file=farm_file)
    except ValueError as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {error}") from error


@router.post(
    "/upload/confirm",
    response_model=ApplyFarmUpdateResponse,
    tags=["Upload"],
    summary="Apply selected upload categories to the active farm",
)
def upload_confirm(request: ApplyFarmUpdateRequest):
    try:
        return apply_farm_update(request)
    except InvalidFarmDataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/daily-updates/categories",
    tags=["Daily Updates"],
    summary="List daily update categories",
)
def daily_update_categories():
    return {"success": True, "categories": list_daily_update_categories()}


@router.post(
    "/daily-updates",
    response_model=DailyUpdateResponse,
    tags=["Daily Updates"],
    summary="Save daily farm updates",
)
def save_daily_updates(request: DailyUpdateRequest):
    try:
        return apply_daily_updates(request)
    except InvalidFarmDataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


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
