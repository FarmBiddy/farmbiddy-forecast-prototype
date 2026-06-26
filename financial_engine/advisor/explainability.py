"""
Explainability engine for farm financial intelligence outputs.

Produces human-readable explanations for forecasts, risk, simulation,
and sensitivity results.  Designed for advisor-facing reports and future
FastAPI response payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from financial_engine.forecasting.interfaces import ForecastOutput
from financial_engine.forecasting.scenario_analysis import ScenarioComparison
from financial_engine.risk.financial_health import FinancialHealthAssessment, RiskScore
from financial_engine.shared.dairy_model import MonthlyForecastResult
from financial_engine.simulation.monte_carlo import SimulationResult
from financial_engine.simulation.sensitivity_analysis import SensitivityMultiReport, SensitivityReport
from financial_engine.statistics.types import ModelComparisonResult, StatisticalForecastResult


@dataclass
class Explanation:
    """A single explainability statement."""

    subject: str
    detail: str
    contribution: float | None = None
    direction: str = "neutral"
    category: str = "general"


@dataclass
class ExplainabilityReport:
    """Complete explainability package for an analysis run."""

    forecast_explanations: list[Explanation] = field(default_factory=list)
    risk_explanations: list[Explanation] = field(default_factory=list)
    uncertainty_explanations: list[Explanation] = field(default_factory=list)
    business_interpretation: list[str] = field(default_factory=list)
    main_profit_drivers: list[str] = field(default_factory=list)
    main_risk_drivers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _exp(e: Explanation) -> dict[str, Any]:
            return {
                "subject": e.subject,
                "detail": e.detail,
                "contribution": e.contribution,
                "direction": e.direction,
                "category": e.category,
            }

        return {
            "forecast": [_exp(e) for e in self.forecast_explanations],
            "risk": [_exp(e) for e in self.risk_explanations],
            "uncertainty": [_exp(e) for e in self.uncertainty_explanations],
            "business_interpretation": self.business_interpretation,
            "main_profit_drivers": self.main_profit_drivers,
            "main_risk_drivers": self.main_risk_drivers,
        }


class ExplainabilityEngine:
    """
    Generates comprehensive explanations from all engine outputs.

    Every prediction and risk assessment should be accompanied by an
    explanation suitable for financial advisors.
    """

    def explain(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
        risk: RiskScore,
        sensitivity: SensitivityReport,
        statistical_forecast: StatisticalForecastResult | ForecastOutput | None = None,
        model_comparison: ModelComparisonResult | None = None,
        scenarios: ScenarioComparison | None = None,
        multi_sensitivity: SensitivityMultiReport | None = None,
    ) -> ExplainabilityReport:
        """Build a complete explainability report."""
        report = ExplainabilityReport()

        report.forecast_explanations = self._explain_forecast(
            forecast, statistical_forecast, model_comparison
        )
        report.risk_explanations = self._explain_risk(risk)
        report.uncertainty_explanations = self._explain_uncertainty(
            simulation, sensitivity, multi_sensitivity
        )
        report.main_profit_drivers = [
            r.display_name for r in sensitivity.results[:3]
        ]
        if risk.assessment:
            sorted_dims = sorted(
                risk.assessment.dimensions, key=lambda d: d.score, reverse=True
            )
            report.main_risk_drivers = [d.display_name for d in sorted_dims[:3]]
        report.business_interpretation = self._business_interpretation(
            forecast, simulation, risk, sensitivity, scenarios
        )
        return report

    def _explain_forecast(
        self,
        forecast: MonthlyForecastResult,
        statistical: StatisticalForecastResult | ForecastOutput | None,
        comparison: ModelComparisonResult | None,
    ) -> list[Explanation]:
        explanations = [
            Explanation(
                subject="Deterministic Forecast",
                detail=(
                    f"Base-case annual profit €{forecast.total_profit:,.0f} "
                    f"with margin {forecast.profit_margin * 100:.1f}%."
                ),
                category="forecast",
            ),
            Explanation(
                subject="Revenue Driver",
                detail=(
                    f"Milk revenue totals €{forecast.total_revenue:,.0f} "
                    f"from {forecast.assumptions.herd_size} cows."
                ),
                category="forecast",
            ),
        ]
        if statistical is not None:
            model_name = (
                statistical.model_name
                if hasattr(statistical, "model_name")
                else "statistical"
            )
            unc = None
            if hasattr(statistical, "uncertainty") and statistical.uncertainty is not None:
                unc = float(statistical.uncertainty.mean())
            elif hasattr(statistical, "statistical_detail") and statistical.statistical_detail:
                unc = float(statistical.statistical_detail.uncertainty.mean())
            explanations.append(
                Explanation(
                    subject="Statistical Forecast",
                    detail=(
                        f"Selected model '{model_name}' with average uncertainty "
                        f"€{unc:,.0f}." if unc else f"Selected model '{model_name}'."
                    ),
                    category="forecast",
                )
            )
        if comparison and comparison.entries:
            best = comparison.entries[0]
            explanations.append(
                Explanation(
                    subject="Model Selection",
                    detail=(
                        f"Best model: {best.model_name} "
                        f"(RMSE={best.rmse:.2f}, MAE={best.mae:.2f})."
                    ),
                    contribution=best.combined_score,
                    category="model_comparison",
                )
            )
        return explanations

    def _explain_risk(self, risk: RiskScore) -> list[Explanation]:
        explanations = [
            Explanation(
                subject="Financial Health",
                detail=(
                    f"Health score {risk.health_score:.0f}/100, "
                    f"risk tier {risk.tier.value}."
                ),
                contribution=risk.health_score,
                category="risk",
            )
        ]
        if risk.assessment:
            for dim in sorted(risk.assessment.dimensions, key=lambda d: d.score, reverse=True):
                explanations.append(
                    Explanation(
                        subject=dim.display_name,
                        detail=dim.explanation,
                        contribution=dim.score,
                        direction="negative" if dim.score > 50 else "neutral",
                        category="risk",
                    )
                )
        return explanations

    def _explain_uncertainty(
        self,
        simulation: SimulationResult,
        sensitivity: SensitivityReport,
        multi: SensitivityMultiReport | None,
    ) -> list[Explanation]:
        total_impact = sum(r.impact_range for r in sensitivity.results)
        explanations = [
            Explanation(
                subject="Simulation Dispersion",
                detail=(
                    f"Profit std dev €{simulation.std:,.0f}, "
                    f"range €{simulation.worst_case:,.0f} to €{simulation.best_case:,.0f}."
                ),
                contribution=simulation.variance,
                category="uncertainty",
            ),
            Explanation(
                subject="Forecast Confidence",
                detail=(
                    f"80% of simulated outcomes fall between "
                    f"€{simulation.percentile_5:,.0f} and €{simulation.percentile_95:,.0f}."
                ),
                category="uncertainty",
            ),
        ]
        if sensitivity.results:
            top = sensitivity.results[0]
            pct = (top.impact_range / total_impact * 100) if total_impact else 0
            explanations.append(
                Explanation(
                    subject=top.display_name,
                    detail=(
                        f"{top.display_name} contributes {pct:.0f}% of total "
                        f"forecast uncertainty."
                    ),
                    contribution=top.impact_range,
                    category="sensitivity",
                )
            )
        if multi and multi.risk_ranking:
            top_risk = multi.risk_ranking[0]
            explanations.append(
                Explanation(
                    subject=f"Risk: {top_risk.display_name}",
                    detail=f"Highest risk sensitivity driver: {top_risk.display_name}.",
                    contribution=top_risk.risk_impact,
                    category="sensitivity",
                )
            )
        return explanations

    def _business_interpretation(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
        risk: RiskScore,
        sensitivity: SensitivityReport,
        scenarios: ScenarioComparison | None,
    ) -> list[str]:
        lines = [
            (
                f"The farm is expected to generate €{simulation.expected_profit:,.0f} "
                f"annual profit with {simulation.probability_of_loss * 100:.0f}% "
                f"probability of loss."
            ),
            risk.explanation,
        ]
        if forecast.max_funding_requirement > 0:
            lines.append(
                f"A peak funding requirement of €{forecast.max_funding_requirement:,.0f} "
                "indicates periods where external financing may be needed."
            )
        if scenarios and "pessimistic" in scenarios.forecasts:
            pess = scenarios.forecasts["pessimistic"]
            base = scenarios.forecasts.get("base")
            if base:
                delta = pess.total_profit - base.total_profit
                lines.append(
                    f"Under pessimistic conditions profit changes by €{delta:,.0f}."
                )
        if sensitivity.results:
            top = sensitivity.results[0]
            lines.append(
                f"{top.display_name} is the primary profit driver — "
                f"a 10% change shifts profit by €{top.impact_range / 2:,.0f}."
            )
        return lines


# Backwards-compatible alias
ModelExplainer = ExplainabilityEngine
