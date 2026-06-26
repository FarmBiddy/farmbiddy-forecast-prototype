"""
End-to-end analysis pipeline for the FarmBiddy Financial Intelligence Engine.

Production orchestrator wiring forecasting, simulation, risk, advisory,
explainability, charts, and dashboard JSON export.

Designed for standalone execution and future FastAPI integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import DEFAULT_FORECAST_HORIZON, OUTPUTS_DIR
from financial_engine.advisor.explainability import ExplainabilityEngine, ExplainabilityReport
from financial_engine.advisor.recommendations import AdvisoryNarrative, RecommendationEngine
from financial_engine.dashboard import DashboardBuilder
from financial_engine.forecasting.deterministic_forecast import DeterministicForecaster
from financial_engine.forecasting.scenario_analysis import ScenarioAnalyser
from financial_engine.risk.risk_scoring import RiskScore, RiskScorer
from financial_engine.shared.dairy_model import DairyFarmAssumptions
from financial_engine.shared.historical_data import FarmHistoricalData
from financial_engine.simulation.correlation import AdvancedMonteCarloConfig
from financial_engine.simulation.monte_carlo import MonteCarloSimulator, SimulationResult
from financial_engine.simulation.sensitivity_analysis import (
    SensitivityAnalyser,
    SensitivityMultiReport,
    SensitivityReport,
)
from financial_engine.statistics.engine import StatisticalForecastEngine
from financial_engine.statistics.types import ForecastModelType, ModelComparisonResult, StatisticalForecastResult
from financial_engine.utils.charts import ChartBuilder
from financial_engine.utils.exporters import DataExporter

ENGINE_VERSION = "1.0.0"


@dataclass
class AnalysisResult:
    """Complete output from a full pipeline run."""

    forecast: Any
    scenarios: Any
    simulation: SimulationResult
    sensitivity: SensitivityReport
    risk: RiskScore
    advisory: AdvisoryNarrative
    charts: dict[str, str] = field(default_factory=dict)
    json_path: Path | None = None
    statistical_forecast: StatisticalForecastResult | None = None
    model_comparison: ModelComparisonResult | None = None
    dashboard: dict[str, Any] = field(default_factory=dict)
    explainability: ExplainabilityReport | None = None
    multi_sensitivity: SensitivityMultiReport | None = None

    def to_dict(self) -> dict[str, Any]:
        phase = "2_statistical" if self.statistical_forecast else "1_deterministic"
        payload: dict[str, Any] = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "engine_version": ENGINE_VERSION,
                "phase": phase,
            },
            "assumptions": self.forecast.detailed.assumptions.model_dump()
            if self.forecast.detailed
            else {},
            "forecast": self.forecast.detailed.to_dict()
            if self.forecast.detailed
            else {},
            "scenarios": self.scenarios.to_dict(),
            "simulation": self.simulation.to_dict(),
            "sensitivity": self.sensitivity.to_dict(),
            "risk": self.risk.to_dict(),
            "recommendations": self.advisory.to_dict(),
            "statistics": {
                "expected_profit": self.simulation.expected_profit,
                "median_profit": self.simulation.median_profit,
                "variance": self.simulation.variance,
                "probability_of_loss": self.simulation.probability_of_loss,
                "profit_margin": self.forecast.detailed.profit_margin
                if self.forecast.detailed
                else 0,
                "risk_score": self.risk.overall_score,
                "health_score": self.risk.health_score,
                "risk_tier": self.risk.tier.value,
            },
            "charts": self.charts,
            "dashboard": self.dashboard,
        }
        if self.statistical_forecast is not None:
            payload["statistical_forecast"] = self.statistical_forecast.to_dict()
        if self.model_comparison is not None:
            payload["model_comparison"] = self.model_comparison.to_dict()
        if self.multi_sensitivity is not None:
            payload["sensitivity_comprehensive"] = self.multi_sensitivity.to_dict()
        if self.explainability is not None:
            payload["explainability"] = self.explainability.to_dict()
        return payload


class FinancialIntelligencePipeline:
    """
    Production analysis pipeline for the FarmBiddy Financial Intelligence Engine.

    Phase 1 behaviour is preserved when ``historical_data`` is not supplied.
    """

    def __init__(
        self,
        assumptions: DairyFarmAssumptions | None = None,
        output_dir: Path | str | None = None,
        mc_iterations: int = 5_000,
        random_seed: int | None = 42,
        historical_data: FarmHistoricalData | None = None,
        forecast_model: ForecastModelType | str = ForecastModelType.AUTO,
        target_column: str = "monthly_profit",
        advanced_mc: bool = False,
    ) -> None:
        self.assumptions = assumptions or DairyFarmAssumptions()
        self.output_dir = Path(output_dir or OUTPUTS_DIR)
        self.mc_iterations = mc_iterations
        self.random_seed = random_seed
        self.historical_data = historical_data
        self.forecast_model = (
            ForecastModelType(forecast_model)
            if isinstance(forecast_model, str)
            else forecast_model
        )
        self.target_column = target_column
        self.advanced_mc = advanced_mc
        self.charts_dir = self.output_dir / "charts"

    def run(self, horizon: int = DEFAULT_FORECAST_HORIZON) -> AnalysisResult:
        """Execute the full analysis pipeline and export results."""
        self.assumptions = self.assumptions.model_copy(
            update={"horizon_months": horizon}
        )

        # 1. Deterministic forecast (always)
        forecaster = DeterministicForecaster(self.assumptions)
        forecast = forecaster.predict(horizon=horizon)

        # 2. Statistical forecast (optional)
        statistical_forecast: StatisticalForecastResult | None = None
        model_comparison: ModelComparisonResult | None = None
        if self.historical_data is not None:
            stat_engine = StatisticalForecastEngine(self.historical_data)
            statistical_forecast, model_comparison = stat_engine.forecast(
                target_column=self.target_column,
                horizon=horizon,
                model=self.forecast_model,
            )

        # 3. Scenario analysis
        scenarios = ScenarioAnalyser(base_assumptions=self.assumptions).compare()

        # 4. Monte Carlo
        advanced_config = AdvancedMonteCarloConfig() if self.advanced_mc else None
        simulation = MonteCarloSimulator(
            assumptions=self.assumptions,
            advanced_config=advanced_config,
            random_seed=self.random_seed,
        ).run(iterations=self.mc_iterations)

        # 5. Sensitivity (profit + comprehensive)
        sensitivity_analyser = SensitivityAnalyser(self.assumptions)
        sensitivity = sensitivity_analyser.analyse_all()
        multi_sensitivity = sensitivity_analyser.analyse_comprehensive()

        # 6. Risk assessment
        detailed = forecast.detailed
        if detailed is None:
            raise RuntimeError("Forecast did not produce detailed results")
        risk = RiskScorer().score(detailed, simulation)

        # 7. Explainability
        explainability = ExplainabilityEngine().explain(
            forecast=detailed,
            simulation=simulation,
            risk=risk,
            sensitivity=sensitivity,
            statistical_forecast=statistical_forecast,
            model_comparison=model_comparison,
            scenarios=scenarios,
            multi_sensitivity=multi_sensitivity,
        )

        # 8. Recommendations
        advisory = RecommendationEngine().generate(
            forecast=detailed,
            simulation=simulation,
            risk=risk,
            sensitivity=sensitivity,
            scenarios=scenarios,
        )

        # 9. Charts
        charts = ChartBuilder(self.charts_dir).generate_all(
            forecast=detailed,
            scenarios=scenarios,
            simulation=simulation,
            sensitivity=sensitivity,
            risk=risk,
            statistical_forecast=statistical_forecast,
        )

        # 10. Dashboard JSON
        dashboard = DashboardBuilder.build(
            deterministic_forecast=detailed,
            statistical_forecast=statistical_forecast,
            scenarios=scenarios,
            simulation=simulation,
            model_comparison=model_comparison,
            risk=risk,
            recommendations=advisory,
            sensitivity=sensitivity,
            multi_sensitivity=multi_sensitivity,
            explainability=explainability,
        )

        result = AnalysisResult(
            forecast=forecast,
            scenarios=scenarios,
            simulation=simulation,
            sensitivity=sensitivity,
            multi_sensitivity=multi_sensitivity,
            risk=risk,
            advisory=advisory,
            explainability=explainability,
            charts=charts,
            statistical_forecast=statistical_forecast,
            model_comparison=model_comparison,
            dashboard=dashboard,
        )

        # 11. Export
        exporter = DataExporter(self.output_dir)
        result.json_path = exporter.to_json(result.to_dict(), "analysis_results.json")
        exporter.to_json(dashboard, "dashboard_data.json")

        return result
