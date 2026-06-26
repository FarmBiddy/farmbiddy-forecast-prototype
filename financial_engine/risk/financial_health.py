"""
Financial Health and Risk Engine.

Expands the Phase 1 risk scorer into a production-grade assessment covering
liquidity, profitability, debt, cashflow, and volatility dimensions.

Produces both a risk score (0–100, higher = riskier) and a complementary
financial health score (0–100, higher = healthier) for advisor communication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from financial_engine.shared.dairy_model import MonthlyForecastResult
from financial_engine.simulation.monte_carlo import SimulationResult


class RiskTier(str, Enum):
    """Risk classification tiers."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskDimension:
    """Single risk dimension with score and narrative."""

    name: str
    display_name: str
    score: float
    weight: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "score": round(self.score, 2),
            "weight": self.weight,
            "explanation": self.explanation,
        }


@dataclass
class FinancialHealthAssessment:
    """Complete financial health and risk assessment."""

    risk_score: float
    health_score: float
    tier: RiskTier
    dimensions: list[RiskDimension]
    explanation: str
    component_details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": round(self.risk_score, 2),
            "health_score": round(self.health_score, 2),
            "tier": self.tier.value,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "explanation": self.explanation,
            "component_details": self.component_details,
        }


@dataclass
class RiskScore:
    """
    Backwards-compatible risk score container.

    Maps to ``FinancialHealthAssessment`` for existing pipeline consumers.
    """

    overall_score: float
    tier: RiskTier
    components: dict[str, float]
    explanation: str
    component_details: dict[str, str] = field(default_factory=dict)
    health_score: float = 0.0
    assessment: FinancialHealthAssessment | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "overall_score": round(self.overall_score, 2),
            "health_score": round(self.health_score, 2),
            "tier": self.tier.value,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "explanation": self.explanation,
            "component_details": self.component_details,
        }
        if self.assessment:
            payload["assessment"] = self.assessment.to_dict()
        return payload


class FinancialHealthEngine:
    """
    Multi-dimensional financial risk and health assessment engine.

    Dimensions:
        - Liquidity Risk (funding requirement, negative cash probability)
        - Profitability Risk (margin, probability of loss)
        - Debt Risk (debt-to-revenue ratio)
        - Cashflow Risk (monthly profit volatility)
        - Volatility Risk (simulation outcome dispersion)
    """

    DIMENSION_WEIGHTS: dict[str, tuple[float, str]] = {
        "liquidity_risk": (0.22, "Liquidity Risk"),
        "profitability_risk": (0.22, "Profitability Risk"),
        "debt_risk": (0.18, "Debt Risk"),
        "cashflow_risk": (0.20, "Cashflow Risk"),
        "volatility_risk": (0.18, "Volatility Risk"),
    }

    def assess(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
    ) -> FinancialHealthAssessment:
        """Compute full financial health assessment."""
        dimensions = self._compute_dimensions(forecast, simulation)
        risk_score = sum(d.score * d.weight for d in dimensions)
        health_score = max(0.0, min(100.0, 100.0 - risk_score))
        tier = self._classify_tier(risk_score)
        explanation = self._build_explanation(dimensions, tier, simulation, forecast)
        details = self._component_details(dimensions, simulation, forecast)

        return FinancialHealthAssessment(
            risk_score=risk_score,
            health_score=health_score,
            tier=tier,
            dimensions=dimensions,
            explanation=explanation,
            component_details=details,
        )

    def _compute_dimensions(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
    ) -> list[RiskDimension]:
        revenue = forecast.total_revenue
        debt_ratio = forecast.assumptions.total_debt / revenue if revenue else 0.0
        avg_profit = float(forecast.monthly_profit.mean())
        profit_std = float(forecast.monthly_profit.std())
        cv = abs(profit_std / avg_profit) if avg_profit else 1.0

        liquidity = min(
            100.0,
            simulation.probability_funding_requirement * 100 * 0.6
            + (forecast.max_funding_requirement / revenue * 200 if revenue else 0) * 0.4,
        )
        profitability = min(
            100.0,
            simulation.probability_of_loss * 100 * 0.6
            + self._margin_risk(forecast.profit_margin) * 0.4,
        )
        debt = min(100.0, debt_ratio * 50)
        cashflow = min(100.0, cv * 80 + simulation.probability_negative_cash * 20)
        volatility = min(100.0, (simulation.variance ** 0.5) / max(abs(simulation.expected_profit), 1) * 50)

        raw_scores = {
            "liquidity_risk": liquidity,
            "profitability_risk": profitability,
            "debt_risk": debt,
            "cashflow_risk": cashflow,
            "volatility_risk": volatility,
        }

        dimensions: list[RiskDimension] = []
        for key, (weight, display) in self.DIMENSION_WEIGHTS.items():
            score = raw_scores[key]
            dimensions.append(
                RiskDimension(
                    name=key,
                    display_name=display,
                    score=score,
                    weight=weight,
                    explanation=self._dimension_narrative(key, score, forecast, simulation),
                )
            )
        return dimensions

    @staticmethod
    def _margin_risk(margin: float) -> float:
        if margin < 0:
            return 95.0
        if margin < 0.05:
            return 75.0
        if margin < 0.10:
            return 50.0
        if margin < 0.20:
            return 25.0
        return 10.0

    @staticmethod
    def _classify_tier(risk_score: float) -> RiskTier:
        if risk_score < 30:
            return RiskTier.LOW
        if risk_score < 55:
            return RiskTier.MEDIUM
        if risk_score < 75:
            return RiskTier.HIGH
        return RiskTier.CRITICAL

    @staticmethod
    def _dimension_narrative(
        key: str,
        score: float,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
    ) -> str:
        narratives = {
            "liquidity_risk": (
                f"Liquidity risk scored {score:.0f}/100. "
                f"P(funding need)={simulation.probability_funding_requirement * 100:.0f}%, "
                f"peak gap €{forecast.max_funding_requirement:,.0f}."
            ),
            "profitability_risk": (
                f"Profitability risk scored {score:.0f}/100. "
                f"P(loss)={simulation.probability_of_loss * 100:.0f}%, "
                f"margin={forecast.profit_margin * 100:.1f}%."
            ),
            "debt_risk": (
                f"Debt risk scored {score:.0f}/100. "
                f"Total debt €{forecast.assumptions.total_debt:,.0f}."
            ),
            "cashflow_risk": (
                f"Cashflow risk scored {score:.0f}/100. "
                f"P(negative cash)={simulation.probability_negative_cash * 100:.0f}%."
            ),
            "volatility_risk": (
                f"Volatility risk scored {score:.0f}/100. "
                f"Profit std dev €{simulation.std:,.0f}."
            ),
        }
        return narratives.get(key, f"{key} scored {score:.0f}/100.")

    def _build_explanation(
        self,
        dimensions: list[RiskDimension],
        tier: RiskTier,
        simulation: SimulationResult,
        forecast: MonthlyForecastResult,
    ) -> str:
        top = max(dimensions, key=lambda d: d.score)
        health = max(0.0, 100.0 - sum(d.score * d.weight for d in dimensions))
        return (
            f"Financial health score: {health:.0f}/100 ({tier.value.title()} risk). "
            f"Primary concern: {top.display_name} ({top.score:.0f}/100). "
            f"P(loss)={simulation.probability_of_loss * 100:.0f}%. "
            f"Expected profit €{simulation.expected_profit:,.0f}."
        )

    def _component_details(
        self,
        dimensions: list[RiskDimension],
        simulation: SimulationResult,
        forecast: MonthlyForecastResult,
    ) -> dict[str, str]:
        details = {d.name: d.explanation for d in dimensions}
        details["probability_of_loss"] = f"{simulation.probability_of_loss * 100:.1f}% chance of annual loss"
        details["profit_margin"] = f"Annual profit margin {forecast.profit_margin * 100:.1f}%"
        return details


class RiskScorer:
    """
    Backwards-compatible facade over ``FinancialHealthEngine``.

    Existing pipeline code continues to call ``RiskScorer().score(...)``.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._engine = FinancialHealthEngine()
        self._legacy_weights = weights

    def score(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
    ) -> RiskScore:
        assessment = self._engine.assess(forecast, simulation)
        components = {d.name: d.score for d in assessment.dimensions}
        components.update(self._legacy_components(forecast, simulation))
        return RiskScore(
            overall_score=assessment.risk_score,
            tier=assessment.tier,
            components=components,
            explanation=assessment.explanation,
            component_details=assessment.component_details,
            health_score=assessment.health_score,
            assessment=assessment,
        )

    def compute_components(
        self,
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
    ) -> dict[str, float]:
        """Backwards-compatible component accessor."""
        dims = {d.name: d.score for d in self._engine.assess(forecast, simulation).dimensions}
        dims.update(self._legacy_components(forecast, simulation))
        return dims

    @staticmethod
    def _legacy_components(
        forecast: MonthlyForecastResult,
        simulation: SimulationResult,
    ) -> dict[str, float]:
        """Phase 1 component keys preserved for backwards compatibility."""
        revenue = forecast.total_revenue
        avg_profit = float(forecast.monthly_profit.mean())
        profit_std = float(forecast.monthly_profit.std())
        debt_ratio_val = forecast.assumptions.total_debt / revenue if revenue else 0.0
        cv = abs(profit_std / avg_profit) if avg_profit else 1.0
        return {
            "probability_of_loss": min(100.0, simulation.probability_of_loss * 100),
            "cashflow_stability": min(100.0, cv * 100),
            "funding_requirement": min(
                100.0, (forecast.max_funding_requirement / revenue * 200) if revenue else 0.0
            ),
            "debt_ratio": min(100.0, debt_ratio_val * 50),
            "profit_margin": FinancialHealthEngine._margin_risk(forecast.profit_margin),
        }
