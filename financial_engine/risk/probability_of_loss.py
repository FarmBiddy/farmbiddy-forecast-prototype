"""
Probability of loss calculations for farm financial outcomes.

This module will eventually contain:
- Loss probability from Monte Carlo outcome distributions
- Value-at-Risk (VaR) and Conditional VaR for farm margins
- Probability of negative net income over a planning horizon
- Integration with simulation results for empirical loss estimates
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LossProbabilityResult:
    """Probability metrics for financial loss events."""

    probability_of_loss: float
    value_at_risk_95: float
    conditional_var_95: float
    threshold: float


class ProbabilityOfLossCalculator:
    """
    Estimates the likelihood and severity of financial losses.

    Future responsibilities:
    - Consume Monte Carlo or historical outcome distributions
    - Support configurable loss thresholds (break-even, loan covenant)
    - Report loss probabilities at multiple confidence levels
    """

    def __init__(self, loss_threshold: float = 0.0) -> None:
        self.loss_threshold = loss_threshold

    def calculate(self, outcomes: np.ndarray) -> LossProbabilityResult:
        """
        Compute placeholder loss metrics from an outcome distribution.

        Full VaR/CVaR calculations will be implemented later.
        """
        if len(outcomes) == 0:
            return LossProbabilityResult(
                probability_of_loss=0.0,
                value_at_risk_95=0.0,
                conditional_var_95=0.0,
                threshold=self.loss_threshold,
            )
        below_threshold = outcomes < self.loss_threshold
        prob_loss = float(np.mean(below_threshold))
        return LossProbabilityResult(
            probability_of_loss=prob_loss,
            value_at_risk_95=float(np.percentile(outcomes, 5)),
            conditional_var_95=float(outcomes[outcomes <= np.percentile(outcomes, 5)].mean())
            if below_threshold.any()
            else 0.0,
            threshold=self.loss_threshold,
        )
