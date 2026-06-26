"""
Probability distributions for Monte Carlo simulation (Phase 2).

Supports Normal, Triangular, Lognormal, and Uniform distributions.
Phase 1 simple normal sampling remains available when ``advanced_config``
is not provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np


class DistributionType(str, Enum):
    NORMAL = "normal"
    TRIANGULAR = "triangular"
    LOGNORMAL = "lognormal"
    UNIFORM = "uniform"


@dataclass
class VariableDistribution:
    """
    Distribution specification for a single stochastic variable.

    Parameters depend on distribution type:
        normal:      mean, std (absolute or as multiplier of mean)
        triangular:  low, mode, high
        lognormal:   mean, sigma (of underlying normal)
        uniform:     low, high
    """

    name: str
    dist_type: DistributionType
    params: dict[str, float]
    as_multiplier: bool = True

    def sample(self, rng: np.random.Generator, n: int = 1) -> np.ndarray:
        """Draw ``n`` samples from this distribution."""
        p = self.params
        dt = self.dist_type

        if dt == DistributionType.NORMAL:
            mean = p.get("mean", 1.0)
            std = p.get("std", 0.08)
            samples = rng.normal(mean, std, size=n)
        elif dt == DistributionType.TRIANGULAR:
            samples = rng.triangular(
                p.get("low", 0.85), p.get("mode", 1.0), p.get("high", 1.15), size=n
            )
        elif dt == DistributionType.LOGNORMAL:
            mean = p.get("mean", 0.0)
            sigma = p.get("sigma", 0.08)
            samples = rng.lognormal(mean, sigma, size=n)
        elif dt == DistributionType.UNIFORM:
            samples = rng.uniform(p.get("low", 0.9), p.get("high", 1.1), size=n)
        else:
            samples = np.ones(n)

        if self.as_multiplier:
            return np.clip(samples, 0.5, 2.0)
        return samples

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dist_type": self.dist_type.value,
            "params": self.params,
            "as_multiplier": self.as_multiplier,
        }


def default_farm_distributions() -> list[VariableDistribution]:
    """
    Sensible default distributions for dairy farm Monte Carlo.

    Distribution choice rationale:
        milk_price   → triangular (bounded market swings)
        milk_yield   → normal (production variation)
        feed_costs   → lognormal (cost spikes, right-skewed)
        operating    → uniform (moderate uncertainty)
        interest     → normal (rate adjustments, absolute not multiplier)
        inflation    → triangular
        unexpected   → lognormal (severity of one-off costs)
    """
    return [
        VariableDistribution(
            "milk_price",
            DistributionType.TRIANGULAR,
            {"low": 0.88, "mode": 1.0, "high": 1.12},
        ),
        VariableDistribution(
            "milk_yield",
            DistributionType.NORMAL,
            {"mean": 1.0, "std": 0.05},
        ),
        VariableDistribution(
            "feed_costs",
            DistributionType.LOGNORMAL,
            {"mean": 0.0, "sigma": 0.10},
        ),
        VariableDistribution(
            "operating_costs",
            DistributionType.UNIFORM,
            {"low": 0.92, "high": 1.08},
        ),
        VariableDistribution(
            "labour_costs",
            DistributionType.NORMAL,
            {"mean": 1.0, "std": 0.06},
        ),
        VariableDistribution(
            "interest_rate",
            DistributionType.NORMAL,
            {"mean": 0.0, "std": 0.008},
            as_multiplier=False,
        ),
        VariableDistribution(
            "inflation",
            DistributionType.TRIANGULAR,
            {"low": -0.01, "mode": 0.0, "high": 0.02},
            as_multiplier=False,
        ),
        VariableDistribution(
            "unexpected_expense",
            DistributionType.LOGNORMAL,
            {"mean": 8.0, "sigma": 0.5},
            as_multiplier=False,
        ),
    ]
