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
    FarmerAdvisorRequest,
    FarmerAdvisorResponse,
    FarmerReportRequest,
    FarmerReportResponse,
    FarmerReportPreviewResponse,
    SectorListResponse,
    FarmerHistoricalDataResponse,
    CashFlowBudgetResponse,
    CashflowActionRequest,
    CashflowActionResponse,
    CashflowActionsTestAllResponse,
)
from models.financial_record import (
    FinancialRecordCreate,
    FinancialRecordDeleteResponse,
    FinancialRecordListResponse,
    FinancialRecordResponse,
    FinancialRecordUpdate,
    IncomeExpenseSummaryResponse,
)
from models.category_budget import (
    CategoryBudgetAnnualCreate,
    CategoryBudgetDeleteResponse,
    CategoryBudgetListResponse,
    CategoryBudgetMonthlyCreate,
    CategoryBudgetResponse,
    CategoryBudgetUpdate,
    CategoryBudgetVsActualResponse,
)
from models.document import (
    DocumentCreate,
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from services.chart_service import get_chart_info, list_chart_files
from services.comparison_service import benchmark_forecasts, compare_forecasts, list_forecast_history
from services.financial_intelligence_service import ask_farm_advisor, get_financial_intelligence
from services.advisor_service import ask_farm_intelligence
from services.report_service import generate_farmer_report, get_report_preview
from services.farmer_dashboard_service import (
    get_farmer_dashboard_preview,
    get_farmer_profile,
    get_sectors_list,
    list_farms_for_selector,
    run_advanced_forecast,
    run_farmer_analysis,
    run_monte_carlo_for_farm,
    get_farmer_historical_data,
    get_cashflow_budget_comparison,
    resolve_farm_file,
)
from services.scenario_sandbox_service import (
    run_scenario_sandbox,
    run_cashflow_action,
    run_all_cashflow_actions,
)
from services.forecast_service import (
    list_available_farms,
    run_chart_generation,
    run_forecast,
    run_multi_farm_analysis,
    run_sandbox_forecast,
)
from services.income_expense_service import build_income_expense_summary
from services.financial_record_service import (
    FinancialRecordNotFoundError,
    add_financial_record,
    delete_financial_record,
    list_financial_records,
    update_financial_record,
)
from services.category_budget_service import (
    CategoryBudgetNotFoundError,
    delete_category_budget,
    list_category_budgets,
    set_annual_budget,
    set_monthly_budget,
    update_category_budget,
)
from services.category_variance_service import build_category_budget_vs_actual
from services.document_service import (
    DocumentNotFoundError,
    add_document,
    delete_document,
    list_documents,
    update_document,
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


@router.get(
    "/farmer/historical-data",
    response_model=FarmerHistoricalDataResponse,
    tags=["Farmer Edition"],
    summary="Historical monthly data for selected sectors",
)
def farmer_historical_data(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        return FarmerHistoricalDataResponse(**get_farmer_historical_data(
            farm_id, _parse_sectors_query(sectors),
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get(
    "/farmer/cashflow-budget",
    response_model=CashFlowBudgetResponse,
    tags=["Farmer Edition"],
    summary="Monthly cash-flow budget vs. actual comparison",
)
def farmer_cashflow_budget(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        return CashFlowBudgetResponse(**get_cashflow_budget_comparison(
            farm_id, _parse_sectors_query(sectors),
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get(
    "/farmer/income-expenses",
    response_model=IncomeExpenseSummaryResponse,
    tags=["Farmer Edition"],
    summary="Where money came from and where it went, by category",
)
def farmer_income_expenses(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        payload = build_income_expense_summary(farm_file, _parse_sectors_query(sectors))
        return IncomeExpenseSummaryResponse(**payload)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get(
    "/farmer/financial-records",
    response_model=FinancialRecordListResponse,
    tags=["Farmer Edition"],
    summary="List manually entered income/expense records",
)
def farmer_list_financial_records(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
    record_type: Optional[str] = Query(default=None, description="income or expense"),
    category: Optional[str] = Query(default=None),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        records = list_financial_records(
            farm_file,
            sectors=_parse_sectors_query(sectors),
            record_type=record_type,
            category=category,
        )
        return FinancialRecordListResponse(success=True, farm_file=farm_file, records=records, count=len(records))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/farmer/financial-records",
    response_model=FinancialRecordResponse,
    tags=["Farmer Edition"],
    summary="Add a manual income or expense record",
)
def farmer_add_financial_record(
    record: FinancialRecordCreate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        created, duplicate = add_financial_record(farm_file, record.model_dump())
        return FinancialRecordResponse(
            success=True,
            record=created,
            possible_duplicate=duplicate is not None,
            duplicate_of=duplicate.get("id") if duplicate else None,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put(
    "/farmer/financial-records/{record_id}",
    response_model=FinancialRecordResponse,
    tags=["Farmer Edition"],
    summary="Edit a manual income or expense record",
)
def farmer_update_financial_record(
    record_id: str,
    changes: FinancialRecordUpdate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        updated = update_financial_record(farm_file, record_id, changes.model_dump(exclude_unset=True))
        return FinancialRecordResponse(success=True, record=updated)
    except FinancialRecordNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Financial record not found: {error}") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete(
    "/farmer/financial-records/{record_id}",
    response_model=FinancialRecordDeleteResponse,
    tags=["Farmer Edition"],
    summary="Delete a manual income or expense record",
)
def farmer_delete_financial_record(
    record_id: str,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        delete_financial_record(farm_file, record_id)
        return FinancialRecordDeleteResponse(success=True, deleted_id=record_id)
    except FinancialRecordNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Financial record not found: {error}") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/farmer/documents",
    response_model=DocumentListResponse,
    tags=["Farmer Edition"],
    summary="List invoices and receipts (P1.2)",
)
def farmer_list_documents(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
    document_type: Optional[str] = Query(default=None, description="invoice or receipt"),
    payment_status: Optional[str] = Query(default=None, description="unpaid or paid"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        documents = list_documents(
            farm_file,
            sectors=_parse_sectors_query(sectors),
            document_type=document_type,
            payment_status=payment_status,
        )
        return DocumentListResponse(success=True, farm_file=farm_file, documents=documents, count=len(documents))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/farmer/documents",
    response_model=DocumentResponse,
    tags=["Farmer Edition"],
    summary="Add an invoice or receipt (P1.2)",
)
def farmer_add_document(
    document: DocumentCreate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        created = add_document(farm_file, document.model_dump())
        return DocumentResponse(success=True, document=created)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put(
    "/farmer/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["Farmer Edition"],
    summary="Edit an invoice or receipt (P1.2)",
)
def farmer_update_document(
    document_id: str,
    changes: DocumentUpdate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        updated = update_document(farm_file, document_id, changes.model_dump(exclude_unset=True))
        return DocumentResponse(success=True, document=updated)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Document not found: {error}") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete(
    "/farmer/documents/{document_id}",
    response_model=DocumentDeleteResponse,
    tags=["Farmer Edition"],
    summary="Delete an invoice or receipt (P1.2)",
)
def farmer_delete_document(
    document_id: str,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        delete_document(farm_file, document_id)
        return DocumentDeleteResponse(success=True, deleted_id=document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Document not found: {error}") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/farmer/category-budgets",
    response_model=CategoryBudgetListResponse,
    tags=["Farmer Edition"],
    summary="List category-level budgets (P0.3)",
)
def farmer_list_category_budgets(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
    record_type: Optional[str] = Query(default=None, description="income or expense"),
    category: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        budgets = list_category_budgets(
            farm_file,
            sectors=_parse_sectors_query(sectors),
            record_type=record_type,
            category=category,
            year=year,
        )
        return CategoryBudgetListResponse(success=True, farm_file=farm_file, budgets=budgets, count=len(budgets))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/farmer/category-budget-vs-actual",
    response_model=CategoryBudgetVsActualResponse,
    tags=["Farmer Edition"],
    summary="Category-level Budget vs Actual: which categories are ahead/behind (P0.3)",
)
def farmer_category_budget_vs_actual(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        payload = build_category_budget_vs_actual(farm_file, _parse_sectors_query(sectors) or [])
        return CategoryBudgetVsActualResponse(**payload)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/category-budgets/monthly",
    response_model=CategoryBudgetResponse,
    tags=["Farmer Edition"],
    summary="Set (or replace) one category's budget for one month",
)
def farmer_set_monthly_category_budget(
    budget: CategoryBudgetMonthlyCreate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        created = set_monthly_budget(farm_file, budget.model_dump())
        return CategoryBudgetResponse(success=True, budgets=[created])
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/category-budgets/annual",
    response_model=CategoryBudgetResponse,
    tags=["Farmer Edition"],
    summary="Set one category's annual budget, split evenly across 12 months",
)
def farmer_set_annual_category_budget(
    budget: CategoryBudgetAnnualCreate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        created = set_annual_budget(farm_file, budget.model_dump())
        return CategoryBudgetResponse(success=True, budgets=created)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put(
    "/farmer/category-budgets/{budget_id}",
    response_model=CategoryBudgetResponse,
    tags=["Farmer Edition"],
    summary="Edit a category budget's amount/notes",
)
def farmer_update_category_budget(
    budget_id: str,
    changes: CategoryBudgetUpdate,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        updated = update_category_budget(farm_file, budget_id, changes.model_dump(exclude_unset=True))
        return CategoryBudgetResponse(success=True, budgets=[updated])
    except CategoryBudgetNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Category budget not found: {error}") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete(
    "/farmer/category-budgets/{budget_id}",
    response_model=CategoryBudgetDeleteResponse,
    tags=["Farmer Edition"],
    summary="Delete a category budget",
)
def farmer_delete_category_budget(
    budget_id: str,
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        delete_category_budget(farm_file, budget_id)
        return CategoryBudgetDeleteResponse(success=True, deleted_id=budget_id)
    except CategoryBudgetNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Category budget not found: {error}") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
        body = request.model_dump()
        sectors = body.pop("sectors", None)
        payload = run_scenario_sandbox(farm_file, body, sectors=sectors)
        return ScenarioSandboxResponse(**payload)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/farmer/cashflow-action",
    response_model=CashflowActionResponse,
    tags=["Farmer Edition"],
    summary="Test one practical cash-flow action (Teagasc item 6)",
)
def farmer_cashflow_action(request: CashflowActionRequest):
    try:
        farm_file = resolve_farm_file(request.farm_file)
        body = request.model_dump()
        action = body.pop("action")
        body.pop("farm_file", None)
        sectors = body.pop("sectors", None)
        payload = run_cashflow_action(farm_file, action, body, sectors=sectors)
        return CashflowActionResponse(**payload)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get(
    "/farmer/cashflow-actions",
    response_model=CashflowActionsTestAllResponse,
    tags=["Farmer Edition"],
    summary="Test all 5 practical cash-flow actions with auto-detected defaults",
)
def farmer_cashflow_actions(
    farm_id: Optional[str] = Query(default=None, alias="farm_file"),
    sectors: Optional[str] = Query(default=None, description="Comma-separated: dairy,beef,lamb"),
):
    try:
        farm_file = resolve_farm_file(farm_id)
        payload = run_all_cashflow_actions(farm_file, _parse_sectors_query(sectors))
        return CashflowActionsTestAllResponse(**payload)
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


@router.post(
    "/farmer/advisor",
    response_model=FarmerAdvisorResponse,
    tags=["Farmer Edition"],
    summary="Farm Intelligence — rule-based advisor with sector-aware routing",
)
def farmer_advisor(request: FarmerAdvisorRequest):
    try:
        return FarmerAdvisorResponse(**ask_farm_intelligence(
            request.question,
            request.farm_file,
            sectors=request.sectors,
        ))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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
