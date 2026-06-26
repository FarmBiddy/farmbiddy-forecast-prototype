"""
Deterministic (rule-based) forecasting for dairy farm financial outcomes.

Delegates all calculations to ``DairyFinancialModel`` so that Phase 2
statistical and Phase 3 ML forecasters can return the same
``MonthlyForecastResult`` type via ``BaseForecaster``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from financial_engine.shared.dairy_model import (
    DairyFarmAssumptions,
    DairyFinancialModel,
    MonthlyForecastResult,
    ScenarioModifiers,
)


@dataclass
class ForecastResult:
    """
    Lightweight summary wrapper for the BaseForecaster interface.

    Full line-item detail lives in ``MonthlyForecastResult``.
    """

    periods: pd.DatetimeIndex
    values: pd.Series
    model_name: str
    metadata: dict[str, str]
    detailed: MonthlyForecastResult | None = None


class BaseForecaster(ABC):
    """
    Abstract base for all forecasting implementations.

    Phase 2 (ARIMA, ETS, Prophet) and Phase 3 (ML) models will subclass
    this and return ``ForecastResult`` with a populated ``detailed`` field.
    """

    @abstractmethod
    def fit(self, historical_data: pd.DataFrame | None = None) -> None:
        """Train or configure the forecaster on historical data."""

    @abstractmethod
    def predict(self, horizon: int | None = None) -> ForecastResult:
        """Generate a forecast for the specified number of periods."""


class DeterministicForecaster(BaseForecaster):
    """
    Rule-based 12-month dairy farm forecast using configurable assumptions.

    Produces monthly line items:
        Milk Revenue, Feed/Labour/Vet/Operating Costs, Interest,
        Debt Repayments, Monthly Profit, Cash Balance, Funding Requirement.
    """

    def __init__(
        self,
        assumptions: DairyFarmAssumptions | None = None,
        modifiers: ScenarioModifiers | None = None,
    ) -> None:
        self.assumptions = assumptions or DairyFarmAssumptions()
        self.modifiers = modifiers or ScenarioModifiers()
        self._historical_data: pd.DataFrame | None = None

    def fit(self, historical_data: pd.DataFrame | None = None) -> None:
        """Store historical data for future calibration (Phase 2)."""
        if historical_data is not None:
            self._historical_data = historical_data.copy()

    def predict(self, horizon: int | None = None) -> ForecastResult:
        """Run the deterministic monthly forecast."""
        if horizon is not None:
            self.assumptions = self.assumptions.model_copy(
                update={"horizon_months": horizon}
            )
        detailed = DairyFinancialModel.compute_forecast(
            self.assumptions, self.modifiers
        )
        return ForecastResult(
            periods=detailed.periods,
            values=detailed.monthly_profit,
            model_name=detailed.model_name,
            metadata={
                "scenario": self.assumptions.scenario_name,
                "total_profit": f"{detailed.total_profit:.2f}",
                "profit_margin": f"{detailed.profit_margin:.4f}",
            },
            detailed=detailed,
        )

    def predict_detailed(self, horizon: int | None = None) -> MonthlyForecastResult:
        """Convenience accessor returning the full monthly breakdown."""
        return self.predict(horizon=horizon).detailed  # type: ignore[return-value]
