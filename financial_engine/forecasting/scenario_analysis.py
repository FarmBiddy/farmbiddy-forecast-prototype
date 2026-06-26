"""
Scenario analysis — Base, Optimistic, and Pessimistic dairy farm futures.

Each scenario applies configurable multipliers to milk price, yield, feed
costs, operating costs, inflation, and interest rates, then runs the shared
``DairyFinancialModel`` and returns comparison tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from financial_engine.shared.dairy_model import (
    SCENARIO_PRESETS,
    DairyFarmAssumptions,
    DairyFinancialModel,
    MonthlyForecastResult,
    ScenarioModifiers,
)


@dataclass
class ScenarioDefinition:
    """Describes a single financial scenario."""

    name: str
    modifiers: ScenarioModifiers
    description: str = ""


@dataclass
class ScenarioComparison:
    """Results from comparing multiple scenarios."""

    scenario_names: list[str]
    comparison_table: pd.DataFrame
    forecasts: dict[str, MonthlyForecastResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_names": self.scenario_names,
            "comparison": self.comparison_table.to_dict(orient="index"),
            "forecasts": {k: v.to_dict() for k, v in self.forecasts.items()},
        }


class ScenarioAnalyser:
    """
    Runs Base / Optimistic / Pessimistic scenarios and compares outcomes.

    Custom scenarios can be registered via ``add_scenario``.
    """

    COMPARISON_METRICS = [
        "total_revenue",
        "total_profit",
        "profit_margin",
        "min_cash_balance",
        "max_funding_requirement",
    ]

    def __init__(
        self,
        base_assumptions: DairyFarmAssumptions | None = None,
        scenarios: list[ScenarioDefinition] | None = None,
    ) -> None:
        self.base_assumptions = base_assumptions or DairyFarmAssumptions()
        if scenarios is None:
            self.scenarios = self._default_scenarios()
        else:
            self.scenarios = scenarios

    @staticmethod
    def _default_scenarios() -> list[ScenarioDefinition]:
        return [
            ScenarioDefinition(
                name="base",
                modifiers=SCENARIO_PRESETS["base"],
                description="Current assumptions with no adjustments",
            ),
            ScenarioDefinition(
                name="optimistic",
                modifiers=SCENARIO_PRESETS["optimistic"],
                description="Higher milk price/yield, lower costs, lower rates",
            ),
            ScenarioDefinition(
                name="pessimistic",
                modifiers=SCENARIO_PRESETS["pessimistic"],
                description="Lower milk price/yield, higher costs, higher rates",
            ),
        ]

    def add_scenario(self, scenario: ScenarioDefinition) -> None:
        self.scenarios.append(scenario)

    def run_scenario(self, scenario: ScenarioDefinition) -> MonthlyForecastResult:
        """Execute a single scenario through the shared financial model."""
        tagged = self.base_assumptions.model_copy(
            update={"scenario_name": scenario.name}
        )
        return DairyFinancialModel.compute_forecast(tagged, scenario.modifiers)

    def compare(self) -> ScenarioComparison:
        """Run all scenarios and build a side-by-side comparison table."""
        forecasts: dict[str, MonthlyForecastResult] = {}
        rows: dict[str, dict[str, float]] = {}

        for scenario in self.scenarios:
            result = self.run_scenario(scenario)
            forecasts[scenario.name] = result
            rows[scenario.name] = {
                "total_revenue": round(result.total_revenue, 2),
                "total_profit": round(result.total_profit, 2),
                "profit_margin": round(result.profit_margin, 4),
                "min_cash_balance": round(result.min_cash_balance, 2),
                "max_funding_requirement": round(result.max_funding_requirement, 2),
                "avg_monthly_profit": round(float(result.monthly_profit.mean()), 2),
            }

        table = pd.DataFrame(rows).T
        table.index.name = "scenario"
        return ScenarioComparison(
            scenario_names=list(forecasts.keys()),
            comparison_table=table,
            forecasts=forecasts,
        )
