"""
Correlated variable sampling for Monte Carlo simulation.

Models economic linkages such as:
    milk_price ↓ → revenue ↓ → cashflow ↓ → funding need ↑
    feed_costs ↔ inflation (positive correlation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from financial_engine.simulation.distributions import (
    VariableDistribution,
    default_farm_distributions,
)


@dataclass
class CorrelationConfig:
    """
    Correlation matrix for stochastic farm variables.

    Variables (default order):
        milk_price, milk_yield, feed_costs, operating_costs,
        interest_rate, inflation
    """

    variable_names: list[str] = field(
        default_factory=lambda: [
            "milk_price",
            "milk_yield",
            "feed_costs",
            "labour_costs",
            "operating_costs",
            "interest_rate",
            "inflation",
        ]
    )
    correlation_matrix: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.correlation_matrix is None:
            self.correlation_matrix = self.default_correlation_matrix()

    @staticmethod
    def default_correlation_matrix() -> np.ndarray:
        """
        Default farm economic correlations.

        milk_price positively correlates with yield (market conditions),
        negatively with feed (input cost pressure), positively with inflation.
        """
        return np.array(
            [
                [1.00, 0.25, 0.30, 0.15, 0.10, 0.15, 0.20],
                [0.25, 1.00, 0.05, 0.05, 0.05, 0.00, 0.05],
                [0.30, 0.05, 1.00, 0.25, 0.40, 0.20, 0.55],
                [0.15, 0.05, 0.25, 1.00, 0.30, 0.10, 0.30],
                [0.10, 0.05, 0.40, 0.30, 1.00, 0.10, 0.35],
                [0.15, 0.00, 0.20, 0.10, 0.10, 1.00, 0.45],
                [0.20, 0.05, 0.55, 0.30, 0.35, 0.45, 1.00],
            ]
        )

    def ensure_positive_definite(self) -> np.ndarray:
        """Nearest positive-definite correction for Cholesky sampling."""
        matrix = self.correlation_matrix.copy()
        eigvals, eigvecs = np.linalg.eigh(matrix)
        eigvals = np.maximum(eigvals, 1e-6)
        return eigvecs @ np.diag(eigvals) @ eigvecs.T

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_names": self.variable_names,
            "correlation_matrix": self.correlation_matrix.tolist(),
        }


@dataclass
class AdvancedMonteCarloConfig:
    """Phase 2 Monte Carlo configuration with distributions and correlation."""

    distributions: list[VariableDistribution] = field(
        default_factory=default_farm_distributions
    )
    correlation: CorrelationConfig = field(default_factory=CorrelationConfig)
    unexpected_expense_probability: float = 0.20

    def to_dict(self) -> dict[str, Any]:
        return {
            "distributions": [d.to_dict() for d in self.distributions],
            "correlation": self.correlation.to_dict(),
            "unexpected_expense_probability": self.unexpected_expense_probability,
        }


class CorrelatedSampler:
    """Generate correlated standard normal samples via Cholesky decomposition."""

    def __init__(self, config: CorrelationConfig, rng: np.random.Generator) -> None:
        self.config = config
        self.rng = rng
        self._cholesky = np.linalg.cholesky(config.ensure_positive_definite())

    def sample(self) -> dict[str, float]:
        """Draw one correlated sample set mapped to distribution quantiles."""
        z = self.rng.standard_normal(len(self.config.variable_names))
        correlated = self._cholesky @ z
        # Map to (0,1) via normal CDF for copula-style marginal application
        from scipy.stats import norm

        uniforms = norm.cdf(correlated)
        return {
            name: float(u)
            for name, u in zip(self.config.variable_names, uniforms, strict=True)
        }


def apply_distribution_with_quantile(
    dist: VariableDistribution,
    quantile: float,
    rng: np.random.Generator,
) -> float:
    """
    Sample from distribution using a correlated quantile as seed.

    Uses the quantile to perturb the random draw toward correlated extremes.
    """
    base = dist.sample(rng, n=1000)
    idx = int(np.clip(quantile * 999, 0, 999))
    sorted_samples = np.sort(base)
    return float(sorted_samples[idx])
