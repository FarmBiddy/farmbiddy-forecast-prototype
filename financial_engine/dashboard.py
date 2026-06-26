"""
Dashboard JSON builder for production deployment.

Produces a single structured JSON payload suitable for frontend dashboards
and future FastAPI endpoints.
"""

from __future__ import annotations

from typing import Any

from financial_engine.advisor.explainability import ExplainabilityReport
from financial_engine.advisor.recommendations import AdvisoryNarrative
from financial_engine.forecasting.interfaces import ForecastOutput
from financial_engine.forecasting.scenario_analysis import ScenarioComparison
from financial_engine.risk.financial_health import RiskScore
from financial_engine.shared.dairy_model import MonthlyForecastResult
from financial_engine.simulation.monte_carlo import SimulationResult
from financial_engine.simulation.sensitivity_analysis import SensitivityMultiReport, SensitivityReport
from financial_engine.statistics.diagnostics import residual_analysis
from financial_engine.statistics.types import ModelComparisonResult, StatisticalForecastResult


class DashboardBuilder:
    """Assembles production-ready dashboard JSON from all engine outputs."""

    @staticmethod
    def build(
        deterministic_forecast: MonthlyForecastResult | None = None,
        statistical_forecast: StatisticalForecastResult | ForecastOutput | None = None,
        scenarios: ScenarioComparison | None = None,
        simulation: SimulationResult | None = None,
        model_comparison: ModelComparisonResult | None = None,
        risk: RiskScore | None = None,
        recommendations: AdvisoryNarrative | None = None,
        sensitivity: SensitivityReport | None = None,
        multi_sensitivity: SensitivityMultiReport | None = None,
        explainability: ExplainabilityReport | None = None,
    ) -> dict[str, Any]:
        """Build complete dashboard data structure for API/frontend consumption."""
        dashboard: dict[str, Any] = {"version": "1.0"}

        if deterministic_forecast is not None:
            dashboard["forecast"] = {
                "type": "deterministic",
                "summary": deterministic_forecast.to_dict()["summary"],
                "monthly_profit": {
                    str(p.date()): round(v, 2)
                    for p, v in deterministic_forecast.monthly_profit.items()
                },
                "cash_balance": {
                    str(p.date()): round(v, 2)
                    for p, v in deterministic_forecast.cash_balance.items()
                },
                "cashflow": {
                    str(p.date()): round(v, 2)
                    for p, v in deterministic_forecast.cash_balance.items()
                },
            }

        if statistical_forecast is not None:
            if isinstance(statistical_forecast, ForecastOutput):
                dashboard["statistical_forecast"] = statistical_forecast.to_dict()
                if statistical_forecast.has_intervals:
                    dashboard["confidence_intervals"] = statistical_forecast.to_dict().get(
                        "prediction_interval_95", {}
                    )
            else:
                sf_dict = statistical_forecast.to_dict()
                dashboard["statistical_forecast"] = sf_dict
                dashboard["confidence_intervals"] = {
                    "confidence_95": sf_dict.get("confidence_band_95", {}),
                    "prediction_95": sf_dict.get("prediction_interval_95", {}),
                    "uncertainty": sf_dict.get("uncertainty", {}),
                }
                dashboard["diagnostics"] = {
                    "accuracy": statistical_forecast.diagnostics.to_dict(),
                    "residual_analysis": residual_analysis(statistical_forecast.diagnostics),
                }

        if scenarios is not None:
            dashboard["scenario_analysis"] = {
                "scenarios": scenarios.scenario_names,
                "metrics": scenarios.comparison_table.to_dict(orient="index"),
            }

        if simulation is not None:
            dashboard["simulation"] = simulation.to_dict()

        if model_comparison is not None:
            dashboard["model_comparison"] = model_comparison.to_dict()

        if risk is not None:
            dashboard["risk"] = risk.to_dict()

        if recommendations is not None:
            dashboard["recommendations"] = recommendations.to_dict()

        if sensitivity is not None:
            dashboard["sensitivity_analysis"] = sensitivity.to_dict()

        if multi_sensitivity is not None:
            dashboard["sensitivity_comprehensive"] = multi_sensitivity.to_dict()

        if explainability is not None:
            dashboard["explainability"] = explainability.to_dict()

        return dashboard
