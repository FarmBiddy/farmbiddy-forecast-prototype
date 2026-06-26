"""
Phase 2 statistical forecasting engine — main entry point.

Orchestrates historical data ingestion, model selection, forecasting,
and diagnostics while remaining independent of Phase 1 deterministic logic.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from financial_engine.shared.historical_data import FarmHistoricalData
from financial_engine.statistics.diagnostics import residual_analysis
from financial_engine.statistics.model_selector import ModelSelector
from financial_engine.statistics.types import (
    ForecastModelType,
    ModelComparisonResult,
    StatisticalForecastResult,
)


class StatisticalForecastEngine:
    """
    High-level API for Phase 2 statistical forecasting.

    Usage::

        engine = StatisticalForecastEngine(historical_data)
        result, comparison = engine.forecast(
            target_column="monthly_profit",
            horizon=12,
            model=ForecastModelType.AUTO,
        )
    """

    def __init__(self, historical_data: FarmHistoricalData | pd.DataFrame) -> None:
        if isinstance(historical_data, FarmHistoricalData):
            self._df = historical_data.to_dataframe()
            self._meta = historical_data
        else:
            self._meta = FarmHistoricalData.from_dataframe(historical_data)
            self._df = self._meta.to_dataframe()
        self._selector = ModelSelector()

    @property
    def historical_data(self) -> pd.DataFrame:
        return self._df

    @property
    def available_columns(self) -> list[str]:
        return self._meta.numeric_columns()

    def get_series(self, column: str) -> pd.Series:
        """Return a cleaned monthly series for the given column."""
        return self._meta.get_series(column)

    def forecast(
        self,
        target_column: str = "monthly_profit",
        horizon: int = 12,
        model: ForecastModelType | str = ForecastModelType.AUTO,
    ) -> tuple[StatisticalForecastResult, ModelComparisonResult]:
        """
        Run model selection and produce a forecast with confidence intervals.

        Args:
            target_column: Historical column to forecast.
            horizon: Months ahead.
            model: ``auto`` or a specific ``ForecastModelType``.
        """
        if isinstance(model, str):
            model = ForecastModelType(model)
        series = self.get_series(target_column)
        return self._selector.select_and_forecast(
            series, horizon=horizon, model_type=model, target_column=target_column
        )

    def full_diagnostics(
        self,
        result: StatisticalForecastResult,
    ) -> dict[str, Any]:
        """Return complete diagnostic package for reporting."""
        return {
            "accuracy": result.diagnostics.to_dict(),
            "residual_analysis": residual_analysis(result.diagnostics),
            "model": result.model_name,
            "uncertainty_mean": float(result.uncertainty.mean()),
        }
