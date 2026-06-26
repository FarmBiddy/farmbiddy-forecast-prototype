"""
Pydantic models for the FarmBiddy Financial Forecast API.

Request and response schemas keep the API layer separate from business logic.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared option objects
# ---------------------------------------------------------------------------

class ForecastOutputs(BaseModel):
    """Toggle which forecast sections are calculated and returned."""

    forecast_summary: bool = False
    monthly_forecast: bool = False
    alerts: bool = False
    risk_level: bool = False
    top_risk_drivers: bool = False
    profitability_dashboard: bool = False
    advisory_summary: bool = False
    kpis: bool = False
    scenarios: bool = False
    comparison_metrics: bool = False

    def any_selected(self) -> bool:
        return any(getattr(self, field) for field in self.model_fields)


class SandboxOutputs(BaseModel):
    """Toggle which sandbox forecast sections are returned."""

    forecast_summary: bool = False
    monthly_forecast: bool = False
    alerts: bool = False
    risk_level: bool = False
    top_risk_drivers: bool = False
    profitability_dashboard: bool = False
    advisory_summary: bool = False
    kpis: bool = False
    scenarios: bool = False

    def any_selected(self) -> bool:
        return any(getattr(self, field) for field in self.model_fields)


# ---------------------------------------------------------------------------
# Home & farms
# ---------------------------------------------------------------------------

class ApplicationStatus(BaseModel):
    application: str
    version: str
    status: str


class FarmSummary(BaseModel):
    farm_file: str
    farm_name: str
    milking_cows: Optional[int] = None
    milk_price: Optional[float] = None


class FarmListResponse(BaseModel):
    farms: List[FarmSummary]
    count: int


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

class ForecastRequest(BaseModel):
    farm_file: str = Field(..., description="JSON filename from datasets/, e.g. dairy_farm_1.json")
    outputs: ForecastOutputs = Field(default_factory=ForecastOutputs)
    save_result: bool = True
    generate_charts: bool = False


class ForecastSummary(BaseModel):
    farm_name: str
    generated_at: str
    annual_revenue: float
    annual_costs: float
    annual_profit: float
    profit_margin: float


class KPIBlock(BaseModel):
    feed_cost_ratio: float
    cost_ratio: float
    revenue_per_cow: float
    profit_per_cow: float
    monthly_cashflow: float


class ForecastResponse(BaseModel):
    farm_file: str
    generated_at: str
    saved_to: Optional[str] = None
    forecast_summary: Optional[ForecastSummary] = None
    monthly_forecast: Optional[List[Dict[str, Any]]] = None
    alerts: Optional[List[str]] = None
    risk_level: Optional[str] = None
    top_risk_drivers: Optional[List[Dict[str, Any]]] = None
    profitability_dashboard: Optional[Dict[str, Any]] = None
    advisory_summary: Optional[Dict[str, Any]] = None
    kpis: Optional[KPIBlock] = None
    scenarios: Optional[List[Dict[str, Any]]] = None
    comparison_metrics: Optional[Dict[str, Any]] = None
    charts: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

class ChartGenerationRequest(BaseModel):
    farm_file: str
    charts: List[str] = Field(
        ...,
        description=(
            "Chart types: running_balance, revenue_vs_costs, cost_breakdown, "
            "scenario_profit, kpi_comparison, historical_profit_trend"
        ),
    )


class GeneratedChart(BaseModel):
    chart_type: str
    file_path: str
    file_name: str


class ChartGenerationResponse(BaseModel):
    farm_file: str
    generated_charts: List[GeneratedChart]


class ChartInfo(BaseModel):
    file_name: str
    file_path: str
    chart_type: Optional[str] = None
    farm_name: Optional[str] = None
    created_at: Optional[str] = None
    size_bytes: Optional[int] = None


class ChartListResponse(BaseModel):
    charts: List[ChartInfo]
    count: int


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class SandboxRequest(BaseModel):
    farm_file: str
    changes: Dict[str, Any] = Field(default_factory=dict)
    outputs: SandboxOutputs = Field(default_factory=SandboxOutputs)


class SandboxResponse(BaseModel):
    farm_file: str
    changes_applied: Dict[str, Any]
    generated_at: str
    forecast_summary: Optional[ForecastSummary] = None
    monthly_forecast: Optional[List[Dict[str, Any]]] = None
    alerts: Optional[List[str]] = None
    risk_level: Optional[str] = None
    top_risk_drivers: Optional[List[Dict[str, Any]]] = None
    profitability_dashboard: Optional[Dict[str, Any]] = None
    advisory_summary: Optional[Dict[str, Any]] = None
    kpis: Optional[KPIBlock] = None
    scenarios: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Comparison & benchmarking
# ---------------------------------------------------------------------------

class ComparisonRequest(BaseModel):
    forecast_files: Optional[List[str]] = None
    compare_all: bool = False
    metrics: Optional[List[str]] = None


class ComparisonResponse(BaseModel):
    comparison: List[Dict[str, Any]]
    metrics: List[str]
    count: int


class BenchmarkRequest(BaseModel):
    forecast_files: Optional[List[str]] = None
    compare_all: bool = False


class BenchmarkMetric(BaseModel):
    farm_name: str
    source_file: str
    value: Any


class BenchmarkResponse(BaseModel):
    best_profit_margin: Optional[BenchmarkMetric] = None
    worst_profit_margin: Optional[BenchmarkMetric] = None
    highest_revenue_per_cow: Optional[BenchmarkMetric] = None
    highest_profit_per_cow: Optional[BenchmarkMetric] = None
    lowest_feed_cost_ratio: Optional[BenchmarkMetric] = None
    highest_risk_farm: Optional[BenchmarkMetric] = None


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class ForecastHistoryItem(BaseModel):
    forecast_file: str
    farm_name: str
    generated_at: str
    annual_profit: float
    risk_level: str


class ForecastHistoryResponse(BaseModel):
    forecasts: List[ForecastHistoryItem]
    count: int
    sort_by: str


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Visual interface — multi-farm analysis
# ---------------------------------------------------------------------------

class AnalyseOutputs(BaseModel):
    """Output toggles used by the visual web interface."""

    forecast_summary: bool = True
    monthly_forecast: bool = False
    alerts: bool = False
    risk_level: bool = False
    top_risk_drivers: bool = False
    profitability_dashboard: bool = False
    advisory_summary: bool = False
    scenarios: bool = False
    charts: bool = False
    forecast_comparison: bool = False
    kpis: bool = True


class AnalyseRequest(BaseModel):
    farm_files: List[str] = Field(..., min_length=1)
    outputs: AnalyseOutputs = Field(default_factory=AnalyseOutputs)
    chart_types: Optional[List[str]] = None
    save_result: bool = True


class AnalyseResponse(BaseModel):
    mode: str = Field(..., description="'single' or 'comparison'")
    results: List[Dict[str, Any]]
    comparison: Optional[List[Dict[str, Any]]] = None
    comparison_metrics: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Farmer Edition
# ---------------------------------------------------------------------------

class FarmerProfileResponse(BaseModel):
    success: bool
    farm_file: str
    farm_name: str
    milking_cows: Optional[int] = None
    litres_per_cow: Optional[float] = None
    milk_price: Optional[float] = None
    opening_cash_balance: Optional[float] = None
    milk_processor: Optional[str] = None
    location: Optional[str] = None
    owner_name: Optional[str] = None
    last_updated: Optional[str] = None


class FarmerDashboardResponse(BaseModel):
    success: bool
    profile: Dict[str, Any]
    kpis: List[Dict[str, Any]]
    has_analysis: bool = False
    farms: List[Dict[str, Any]] = Field(default_factory=list)


class FarmerAdvancedForecastResponse(BaseModel):
    success: bool
    farm_file: str
    profile: Dict[str, Any]
    generated_at: Optional[str] = None
    forecast_summary: Optional[Dict[str, Any]] = None
    monthly_forecast: List[Dict[str, Any]] = Field(default_factory=list)
    profitability_dashboard: Optional[Dict[str, Any]] = None
    kpis: Optional[Dict[str, Any]] = None
    alerts: List[str] = Field(default_factory=list)
    risk_level: Optional[str] = None
    top_risk_drivers: List[Dict[str, Any]] = Field(default_factory=list)
    advisory_summary: Optional[Dict[str, Any]] = None
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    monte_carlo: Dict[str, Any] = Field(default_factory=dict)
    charts: Dict[str, str] = Field(default_factory=dict)
    interpretation: str = ""
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    cashflow_chart_data: List[Dict[str, Any]] = Field(default_factory=list)
    profit_chart_data: List[Dict[str, Any]] = Field(default_factory=list)


class FarmerMonteCarloRequest(BaseModel):
    farm_file: Optional[str] = Field(default=None, description="Farm JSON filename")
    iterations: int = Field(default=1000, ge=100, le=10000)


class FarmerMonteCarloResponse(BaseModel):
    success: bool
    farm_file: str
    profile: Dict[str, Any]
    monte_carlo: Dict[str, Any]
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)


class ScenarioSandboxRequest(BaseModel):
    farm_file: Optional[str] = None
    milk_price_cents_change: float = 0
    milk_price_pct_change: float = 0
    feed_pct_change: float = 0
    fertiliser_pct_change: float = 0
    labour_pct_change: float = 0
    vet_pct_change: float = 0
    fuel_pct_change: float = 0
    electricity_pct_change: float = 0
    loan_repayments: Optional[float] = None
    milking_cows: Optional[int] = None
    litres_per_cow: Optional[float] = None
    opening_cash_balance: Optional[float] = None


class ScenarioSandboxResponse(BaseModel):
    success: bool
    farm_file: str
    farm_name: str
    changes_applied: Dict[str, Any] = Field(default_factory=dict)
    comparison: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    base: Dict[str, Any] = Field(default_factory=dict)
    scenario: Dict[str, Any] = Field(default_factory=dict)
    monthly_forecast_base: List[Dict[str, Any]] = Field(default_factory=list)
    monthly_forecast_scenario: List[Dict[str, Any]] = Field(default_factory=list)


class FarmerRunAnalysisRequest(BaseModel):
    farm_file: Optional[str] = Field(default=None, description="Farm JSON filename")


class FinancialIntelligenceResponse(BaseModel):
    success: bool
    farm_file: str
    farm_name: Optional[str] = None
    profile: Dict[str, Any] = Field(default_factory=dict)
    health_score: Dict[str, Any] = Field(default_factory=dict)
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)
    biggest_risks: List[Dict[str, Any]] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    recommended_actions: List[Dict[str, Any]] = Field(default_factory=list)
    plain_summary: str = ""
    alerts: List[str] = Field(default_factory=list)
    forecast_summary: Dict[str, Any] = Field(default_factory=dict)
    advisor_headline: str = ""


class AskAdvisorRequest(BaseModel):
    question: str = Field(..., min_length=1)
    farm_file: Optional[str] = None


class AskAdvisorResponse(BaseModel):
    success: bool
    question: str
    answer: str
    details: List[str] = Field(default_factory=list)


class FarmerReportRequest(BaseModel):
    farm_file: Optional[str] = Field(default=None, description="Farm JSON filename")
    report_type: str = Field(default="full", description="executive | full | scenario | investment")
    report_date: Optional[str] = Field(default=None, description="Display date on cover page")


class FarmerReportResponse(BaseModel):
    success: bool
    farm_file: str
    farm_name: str
    report_type: str
    report_type_label: str
    report_date: str
    filename: str
    download_url: str
    page_count: int
    executive_summary: str
    generated_at: str


class FarmerReportPreviewResponse(BaseModel):
    success: bool
    farm_file: str
    farm_name: str
    report_type: str
    report_type_label: str
    report_date: str
    executive_summary: str
    health_score: Dict[str, Any] = Field(default_factory=dict)
    kpis: Dict[str, Any] = Field(default_factory=dict)
    page_count_estimate: int
    sections: List[str] = Field(default_factory=list)


class FarmerAnalysisResponse(BaseModel):
    success: bool
    generated_at: Optional[str] = None
    profile: Dict[str, Any]
    kpis: List[Dict[str, Any]]
    alerts: List[str] = Field(default_factory=list)
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    health: Dict[str, Any] = Field(default_factory=dict)
    scenario_snapshots: List[Dict[str, Any]] = Field(default_factory=list)
    charts: Dict[str, str] = Field(default_factory=dict)
    monthly_forecast: List[Dict[str, Any]] = Field(default_factory=list)
    profit_chart_data: List[Dict[str, Any]] = Field(default_factory=list)
    cashflow_chart_data: List[Dict[str, Any]] = Field(default_factory=list)
    recent_updates: List[Dict[str, Any]] = Field(default_factory=list)
    upcoming_payments: List[Dict[str, Any]] = Field(default_factory=list)
    forecast_summary: Optional[Dict[str, Any]] = None
    top_risk_drivers: List[Dict[str, Any]] = Field(default_factory=list)

