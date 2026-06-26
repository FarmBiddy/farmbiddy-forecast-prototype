"""
Advisor-facing recommendations with explanatory narratives.

Generates plain-language summaries explaining WHY each risk or opportunity
matters, grounded in forecast, simulation, and sensitivity outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from financial_engine.shared.dairy_model import MonthlyForecastResult
from financial_engine.forecasting.scenario_analysis import ScenarioComparison
from financial_engine.risk.risk_scoring import RiskScore, RiskTier
from financial_engine.simulation.monte_carlo import SimulationResult
from financial_engine.simulation.sensitivity_analysis import SensitivityReport


class RecommendationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Recommendation:
    title: str
    description: str
    priority: RecommendationPriority
    category: str
    rationale: str = ""
    estimated_impact: str = ""


@dataclass
class AdvisoryNarrative:
    """Full advisor-facing narrative with headline and supporting points."""

    headline: str
    summary_paragraphs: list[str]
    recommendations: list[Recommendation]
    key_statistics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "summary_paragraphs": self.summary_paragraphs,
            "recommendations": [
                {
                    "title": r.title,
                    "description": r.description,
                    "rationale": r.rationale,
                    "priority": r.priority.value,
                    "category": r.category,
                    "estimated_impact": r.estimated_impact,
                }
                for r in self.recommendations
            ],
            "key_statistics": self.key_statistics,
        }


class RecommendationEngine:
    """
    Produces advisor-friendly narratives from engine outputs.

    Every recommendation includes a ``rationale`` explaining WHY.
    """

    def generate(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
        risk: RiskScore,
        sensitivity: SensitivityReport,
        scenarios: ScenarioComparison | None = None,
    ) -> AdvisoryNarrative:
        """Build a complete advisory narrative from all analysis modules."""
        paragraphs = self._build_summary_paragraphs(
            forecast, simulation, risk, sensitivity
        )
        recommendations = self._build_recommendations(
            forecast, simulation, risk, sensitivity, scenarios
        )
        headline = self._build_headline(risk, simulation)

        return AdvisoryNarrative(
            headline=headline,
            summary_paragraphs=paragraphs,
            recommendations=recommendations,
            key_statistics={
                "probability_of_loss_pct": round(simulation.probability_of_loss * 100, 1),
                "expected_annual_profit": round(simulation.expected_profit, 2),
                "profit_margin_pct": round(forecast.profit_margin * 100, 1),
                "max_funding_requirement": round(forecast.max_funding_requirement, 2),
                "risk_tier": risk.tier.value,
                "risk_score": round(risk.overall_score, 1),
            },
        )

    def _build_headline(self, risk: RiskScore, simulation: SimulationResult) -> str:
        prob = simulation.probability_of_loss * 100
        tier = risk.tier.value.title()
        return (
            f"{tier} risk profile: {prob:.0f}% probability of annual loss "
            f"with expected profit of €{simulation.expected_profit:,.0f}"
        )

    def _build_summary_paragraphs(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
        risk: RiskScore,
        sensitivity: SensitivityReport,
    ) -> list[str]:
        prob = simulation.probability_of_loss * 100
        top_driver = sensitivity.results[0] if sensitivity.results else None
        driver_text = ""
        if top_driver:
            total_impact = sum(r.impact_range for r in sensitivity.results)
            contribution_pct = (
                (top_driver.impact_range / total_impact * 100) if total_impact else 0
            )
            driver_text = (
                f"{top_driver.display_name} volatility contributes "
                f"{contribution_pct:.0f}% of total forecast uncertainty."
            )

        paragraphs = [
            (
                f"The farm has a {prob:.0f}% probability of making a loss over the "
                f"next 12 months. {driver_text}"
            ).strip(),
            (
                f"Expected annual profit is €{simulation.expected_profit:,.0f} "
                f"(median €{simulation.median_profit:,.0f}), with a 5th–95th "
                f"percentile range of €{simulation.percentile_5:,.0f} to "
                f"€{simulation.percentile_95:,.0f}."
            ),
            risk.explanation,
        ]

        # Yield improvement narrative (sensitivity-driven)
        yield_result = next(
            (r for r in sensitivity.results if r.parameter == "milk_yield"), None
        )
        if yield_result and yield_result.impact_range > 0:
            funding_reduction = forecast.max_funding_requirement * 0.15
            paragraphs.append(
                f"Increasing milk yield by 3% could improve annual profit by "
                f"approximately €{(yield_result.profit_at_high - yield_result.profit_at_base) / 2:,.0f} "
                f"and reduce funding requirements by approximately €{funding_reduction:,.0f}."
            )

        return paragraphs

    def _build_recommendations(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
        risk: RiskScore,
        sensitivity: SensitivityReport,
        scenarios: ScenarioComparison | None,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []

        if simulation.probability_of_loss > 0.25:
            recs.append(
                Recommendation(
                    title="Address profitability risk",
                    description=(
                        f"Loss probability is {simulation.probability_of_loss * 100:.0f}%. "
                        "Review cost structure and revenue drivers."
                    ),
                    rationale=(
                        "Monte Carlo simulation shows more than 1 in 4 scenarios "
                        "result in an annual loss, threatening business resilience."
                    ),
                    priority=RecommendationPriority.URGENT
                    if simulation.probability_of_loss > 0.4
                    else RecommendationPriority.HIGH,
                    category="profitability",
                )
            )

        if forecast.max_funding_requirement > 0:
            recs.append(
                Recommendation(
                    title="Secure liquidity buffer",
                    description=(
                        f"Peak funding requirement of €{forecast.max_funding_requirement:,.0f} "
                        "identified within the forecast horizon."
                    ),
                    rationale=(
                        "Cash balance falls below the minimum threshold in at least one month, "
                        "requiring external funding or overdraft facilities."
                    ),
                    priority=RecommendationPriority.HIGH,
                    category="liquidity",
                    estimated_impact=f"€{forecast.max_funding_requirement:,.0f} funding gap",
                )
            )

        if simulation.probability_funding_requirement > 0.3:
            recs.append(
                Recommendation(
                    title="Review credit facilities",
                    description=(
                        f"{simulation.probability_funding_requirement * 100:.0f}% of simulations "
                        "require external funding."
                    ),
                    rationale=(
                        "Stochastic analysis shows funding need is not a one-off event — "
                        "contingency credit lines should be arranged proactively."
                    ),
                    priority=RecommendationPriority.MEDIUM,
                    category="funding",
                )
            )

        top = sensitivity.results[0] if sensitivity.results else None
        if top:
            recs.append(
                Recommendation(
                    title=f"Monitor {top.display_name}",
                    description=(
                        f"{top.display_name} has the largest impact on profit "
                        f"(€{top.impact_range:,.0f} swing across ±10% range)."
                    ),
                    rationale=(
                        "Sensitivity analysis ranks this variable highest — "
                        "small market movements here have outsized effects on farm viability."
                    ),
                    priority=RecommendationPriority.MEDIUM,
                    category="market_exposure",
                )
            )

        if risk.tier in (RiskTier.HIGH, RiskTier.CRITICAL):
            recs.append(
                Recommendation(
                    title="Develop risk mitigation plan",
                    description=(
                        f"Financial health score {risk.health_score:.0f}/100 "
                        f"indicates {risk.tier.value} risk."
                    ),
                    rationale=risk.explanation,
                    priority=RecommendationPriority.URGENT
                    if risk.tier == RiskTier.CRITICAL
                    else RecommendationPriority.HIGH,
                    category="risk_management",
                )
            )

        feed = next((r for r in sensitivity.results if r.parameter == "feed_costs"), None)
        if feed and feed.impact_range > 0:
            saving = abs(feed.profit_at_high - feed.profit_at_base) / 2
            pct = 5.0
            recs.append(
                Recommendation(
                    title=f"Reduce feed costs by {pct:.0f}%",
                    description=(
                        f"Feed costs are a top profit driver. A {pct:.0f}% reduction "
                        f"could improve profit by approximately €{saving * pct / 10:,.0f}."
                    ),
                    rationale=(
                        "Sensitivity analysis shows feed costs have high elasticity — "
                        "efficiency gains or alternative sourcing directly improve margins."
                    ),
                    priority=RecommendationPriority.MEDIUM,
                    category="cost_reduction",
                    estimated_impact=f"€{saving * pct / 10:,.0f} potential saving",
                )
            )

        yield_r = next((r for r in sensitivity.results if r.parameter == "milk_yield"), None)
        if yield_r and yield_r.impact_range > 0:
            uplift = abs(yield_r.profit_at_high - yield_r.profit_at_base) / 2
            recs.append(
                Recommendation(
                    title="Increase milk production",
                    description=(
                        f"A 3% yield improvement could add approximately €{uplift * 0.3:,.0f} "
                        "to annual profit."
                    ),
                    rationale=(
                        "Milk yield is a key revenue lever — genetics, nutrition, and "
                        "health management can lift output without proportional cost increases."
                    ),
                    priority=RecommendationPriority.MEDIUM,
                    category="revenue",
                )
            )

        if forecast.assumptions.total_debt > forecast.total_revenue * 0.5:
            recs.append(
                Recommendation(
                    title="Reduce debt exposure",
                    description=(
                        f"Debt of €{forecast.assumptions.total_debt:,.0f} exceeds 50% "
                        "of annual revenue."
                    ),
                    rationale=(
                        "Elevated debt increases interest costs and reduces resilience "
                        "to market downturns. Debt restructuring or accelerated repayment "
                        "should be considered."
                    ),
                    priority=RecommendationPriority.MEDIUM,
                    category="debt",
                )
            )

        if forecast.min_cash_balance < forecast.assumptions.minimum_cash_threshold * 1.5:
            recs.append(
                Recommendation(
                    title="Increase cash reserves",
                    description=(
                        f"Minimum cash balance €{forecast.min_cash_balance:,.0f} "
                        "provides limited buffer above the policy threshold."
                    ),
                    rationale=(
                        "Building reserves improves liquidity resilience and reduces "
                        "reliance on emergency credit during low-income months."
                    ),
                    priority=RecommendationPriority.MEDIUM,
                    category="liquidity",
                )
            )

        if simulation.probability_of_loss > 0.35:
            recs.append(
                Recommendation(
                    title="Delay non-essential investment",
                    description=(
                        "High loss probability suggests deferring capital expenditure "
                        "until profitability stabilises."
                    ),
                    rationale=(
                        f"With {simulation.probability_of_loss * 100:.0f}% probability of loss, "
                        "preserving cash for operating needs takes priority over expansion."
                    ),
                    priority=RecommendationPriority.HIGH,
                    category="investment",
                )
            )

        if scenarios and "pessimistic" in scenarios.forecasts:
            pess = scenarios.forecasts["pessimistic"]
            base = scenarios.forecasts.get("base")
            if base and pess.total_profit < 0:
                recs.append(
                    Recommendation(
                        title="Stress-test pessimistic scenario",
                        description=(
                            f"Pessimistic scenario shows annual loss of "
                            f"€{abs(pess.total_profit):,.0f}."
                        ),
                        rationale=(
                            "Under adverse market conditions the farm is loss-making — "
                            "cost reduction or revenue diversification should be evaluated."
                        ),
                        priority=RecommendationPriority.HIGH,
                        category="scenario_planning",
                    )
                )

        return sorted(recs, key=lambda r: list(RecommendationPriority).index(r.priority))

    def get_prioritised(self, narrative: AdvisoryNarrative) -> list[Recommendation]:
        return narrative.recommendations
