"""
Lightweight Monte Carlo simulation for DAIRY FINANCIALS.

Perturbs milk price and key cost drivers using the existing revenue/cost/profit
engine. Does not replace the full Financial Intelligence Monte Carlo module.
"""

from __future__ import annotations

import random
from typing import Any

from forecast_engine.costs import calculate_costs
from forecast_engine.profit import calculate_profit
from forecast_engine.revenue import calculate_revenue


def run_monte_carlo(farm: dict, iterations: int = 1000, seed: int = 42) -> dict[str, Any]:
    """Run a Monte Carlo profit simulation on a farm dict."""
    rng = random.Random(seed)
    profits: list[float] = []
    revenues: list[float] = []

    base_price = float(farm.get("milk_price", 0.42))
    base_feed = float(farm.get("feed", 0))

    for _ in range(iterations):
        scenario = dict(farm)
        scenario["milk_price"] = base_price * rng.uniform(0.90, 1.10)
        scenario["feed"] = base_feed * rng.uniform(0.92, 1.15)
        scenario["fertiliser"] = float(farm.get("fertiliser", 0)) * rng.uniform(0.95, 1.10)
        scenario["labour"] = float(farm.get("labour", 0)) * rng.uniform(0.98, 1.08)
        revenue = calculate_revenue(scenario)
        costs = calculate_costs(scenario)
        profit = calculate_profit(revenue, costs)
        profits.append(profit)
        revenues.append(revenue)

    profits.sort()
    n = len(profits)
    p10 = profits[int(n * 0.10)]
    p50 = profits[int(n * 0.50)]
    p90 = profits[int(n * 0.90)]
    prob_loss = sum(1 for p in profits if p < 0) / n

    if prob_loss > 0.25:
        interpretation = (
            "There is a meaningful chance of making a loss under variable milk prices "
            "and costs. Build cash reserves and review fixed costs."
        )
    elif prob_loss > 0.10:
        interpretation = (
            "Your farm is likely to remain profitable, but winter cash reserves "
            "may become tight in some scenarios."
        )
    else:
        interpretation = (
            "Based on current assumptions, your farm is likely to remain profitable "
            "with manageable downside risk."
        )

    return {
        "iterations": iterations,
        "expected_profit": round(sum(profits) / n, 0),
        "expected_revenue": round(sum(revenues) / n, 0),
        "best_case": round(p90, 0),
        "expected_case": round(p50, 0),
        "worst_case": round(p10, 0),
        "confidence_range": [round(p10, 0), round(p90, 0)],
        "probability_of_loss": round(prob_loss, 4),
        "interpretation": interpretation,
    }
