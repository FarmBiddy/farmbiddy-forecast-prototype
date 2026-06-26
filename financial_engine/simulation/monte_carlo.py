"""
Monte Carlo simulation for probabilistic dairy farm financial outcomes.

Runs ≥5 000 iterations, randomly varying milk price, production, feed costs,
operating costs, unexpected expenses, and interest rates.  Each iteration
delegates to ``DairyFinancialModel.compute_annual_summary``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from financial_engine.shared.dairy_model import (
    DairyFarmAssumptions,
    DairyFinancialModel,
    ScenarioModifiers,
)


@dataclass
class SimulationDistributionConfig:
    """Standard-deviation settings for stochastic variables (as % of base)."""

    milk_price_std_pct: float = 0.08
    milk_yield_std_pct: float = 0.05
    feed_cost_std_pct: float = 0.10
    operating_cost_std_pct: float = 0.08
    interest_rate_std: float = 0.008
    unexpected_expense_mean: float = 3_500.0
    unexpected_expense_probability: float = 0.20


@dataclass
class SimulationResult:
    """Complete output from a Monte Carlo simulation run."""

    iterations: int
    annual_profits: np.ndarray
    min_cash_balances: np.ndarray
    max_funding_requirements: np.ndarray
    expected_profit: float
    median_profit: float
    percentile_5: float
    percentile_95: float
    probability_of_loss: float
    probability_negative_cash: float
    probability_funding_requirement: float
    std: float
    min_outcome: float
    max_outcome: float
    distribution_config: SimulationDistributionConfig = field(
        default_factory=SimulationDistributionConfig
    )
    advanced_config: Any | None = None
    sampling_mode: str = "legacy"
    variance: float = 0.0

    @property
    def best_case(self) -> float:
        """Maximum simulated annual profit."""
        return self.max_outcome

    @property
    def worst_case(self) -> float:
        """Minimum simulated annual profit."""
        return self.min_outcome

    def to_dict(self) -> dict[str, Any]:
        result = {
            "iterations": self.iterations,
            "expected_profit": round(self.expected_profit, 2),
            "median_profit": round(self.median_profit, 2),
            "variance": round(self.variance, 2),
            "std": round(self.std, 2),
            "best_case": round(self.best_case, 2),
            "worst_case": round(self.worst_case, 2),
            "percentile_5": round(self.percentile_5, 2),
            "percentile_95": round(self.percentile_95, 2),
            "probability_of_loss": round(self.probability_of_loss, 4),
            "probability_negative_cash": round(self.probability_negative_cash, 4),
            "probability_funding_requirement": round(self.probability_funding_requirement, 4),
            "sampling_mode": self.sampling_mode,
            "distribution_statistics": {
                "std": round(self.std, 2),
                "variance": round(self.variance, 2),
                "min": round(self.min_outcome, 2),
                "max": round(self.max_outcome, 2),
            },
        }
        if self.advanced_config is not None:
            result["advanced_config"] = self.advanced_config.to_dict()
        return result


class MonteCarloSimulator:
    """
    Stochastic simulator using NumPy random sampling.

    Designed so Phase 2/3 model outputs can replace the deterministic
    ``compute_annual_summary`` call inside each iteration.
    """

    MIN_ITERATIONS = 5_000

    def __init__(
        self,
        assumptions: DairyFarmAssumptions | None = None,
        distribution: SimulationDistributionConfig | None = None,
        advanced_config: Any | None = None,
        random_seed: int | None = None,
    ) -> None:
        self.assumptions = assumptions or DairyFarmAssumptions()
        self.distribution = distribution or SimulationDistributionConfig()
        self.advanced_config = advanced_config
        self._rng = np.random.default_rng(random_seed)

    def _sample_modifiers_legacy(self) -> ScenarioModifiers:
        """Phase 1 simple normal perturbation (backwards compatible)."""
        d = self.distribution
        a = self.assumptions

        milk_price = self._rng.normal(1.0, d.milk_price_std_pct)
        milk_yield = self._rng.normal(1.0, d.milk_yield_std_pct)
        feed = self._rng.normal(1.0, d.feed_cost_std_pct)
        operating = self._rng.normal(1.0, d.operating_cost_std_pct)
        interest_adj = self._rng.normal(0.0, d.interest_rate_std)

        unexpected = 0.0
        expense_month: int | None = None
        if self._rng.random() < d.unexpected_expense_probability:
            unexpected = float(
                self._rng.exponential(d.unexpected_expense_mean)
            )
            expense_month = int(self._rng.integers(0, a.horizon_months))

        return ScenarioModifiers(
            milk_price_multiplier=max(0.5, milk_price),
            milk_yield_multiplier=max(0.5, milk_yield),
            feed_cost_multiplier=max(0.5, feed),
            operating_cost_multiplier=max(0.5, operating),
            interest_rate_adjustment=interest_adj,
            unexpected_expense=unexpected,
            unexpected_expense_month=expense_month,
        )

    def _sample_modifiers_advanced(self) -> ScenarioModifiers:
        """Phase 2 correlated multi-distribution sampling."""
        from financial_engine.simulation.correlation import (
            AdvancedMonteCarloConfig,
            CorrelatedSampler,
            apply_distribution_with_quantile,
        )

        config: AdvancedMonteCarloConfig = self.advanced_config
        sampler = CorrelatedSampler(config.correlation, self._rng)
        quantiles = sampler.sample()
        dist_map = {d.name: d for d in config.distributions}

        def draw(name: str, default: float = 1.0) -> float:
            if name in dist_map and name in quantiles:
                return apply_distribution_with_quantile(
                    dist_map[name], quantiles[name], self._rng
                )
            return default

        unexpected = 0.0
        expense_month: int | None = None
        if self._rng.random() < config.unexpected_expense_probability:
            unexpected = draw("unexpected_expense", 3_500.0)
            expense_month = int(self._rng.integers(0, self.assumptions.horizon_months))

        return ScenarioModifiers(
            milk_price_multiplier=draw("milk_price"),
            milk_yield_multiplier=draw("milk_yield"),
            feed_cost_multiplier=draw("feed_costs"),
            operating_cost_multiplier=draw("operating_costs"),
            labour_cost_multiplier=draw("labour_costs", 1.0),
            interest_rate_adjustment=draw("interest_rate", 0.0),
            inflation_rate_adjustment=draw("inflation", 0.0),
            unexpected_expense=unexpected,
            unexpected_expense_month=expense_month,
        )

    def _sample_modifiers(self) -> ScenarioModifiers:
        """Draw one random scenario modifier set for a single iteration."""
        if self.advanced_config is not None:
            return self._sample_modifiers_advanced()
        return self._sample_modifiers_legacy()

    def run(self, iterations: int = 5_000) -> SimulationResult:
        """
        Execute Monte Carlo simulation.

        Args:
            iterations: Number of simulation paths (minimum 5 000).
        """
        n = max(iterations, self.MIN_ITERATIONS)
        profits = np.zeros(n)
        min_cash = np.zeros(n)
        max_funding = np.zeros(n)
        neg_cash_flags = np.zeros(n, dtype=bool)
        funding_flags = np.zeros(n, dtype=bool)

        for i in range(n):
            modifiers = self._sample_modifiers()
            summary = DairyFinancialModel.compute_annual_summary(
                self.assumptions, modifiers
            )
            profits[i] = summary.annual_profit
            min_cash[i] = summary.min_cash_balance
            max_funding[i] = summary.max_funding_requirement
            neg_cash_flags[i] = summary.had_negative_cash
            funding_flags[i] = summary.had_funding_requirement

        return SimulationResult(
            iterations=n,
            annual_profits=profits,
            min_cash_balances=min_cash,
            max_funding_requirements=max_funding,
            expected_profit=float(np.mean(profits)),
            median_profit=float(np.median(profits)),
            percentile_5=float(np.percentile(profits, 5)),
            percentile_95=float(np.percentile(profits, 95)),
            probability_of_loss=float(np.mean(profits < 0)),
            probability_negative_cash=float(np.mean(neg_cash_flags)),
            probability_funding_requirement=float(np.mean(funding_flags)),
            std=float(np.std(profits)),
            variance=float(np.var(profits)),
            min_outcome=float(np.min(profits)),
            max_outcome=float(np.max(profits)),
            distribution_config=self.distribution,
            advanced_config=self.advanced_config,
            sampling_mode="advanced" if self.advanced_config else "legacy",
        )

    def to_dataframe(self, result: SimulationResult):
        """Convert simulation outcomes to a DataFrame."""
        import pandas as pd

        return pd.DataFrame(
            {
                "iteration": np.arange(result.iterations),
                "annual_profit": result.annual_profits,
                "min_cash_balance": result.min_cash_balances,
                "max_funding_requirement": result.max_funding_requirements,
            }
        )
