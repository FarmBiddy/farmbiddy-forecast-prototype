"""
Abstract base for Phase 2 statistical forecasting models.

Every model (Linear Trend, MA, ETS, Holt, ARIMA) implements this interface
so the model selector and pipeline can treat them uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from financial_engine.statistics.types import (
    ForecastModelType,
    StatisticalForecastResult,
)


class StatisticalModel(ABC):
    """Base class for univariate time-series forecasters."""

    model_type: ForecastModelType
    model_name: str

    def __init__(self) -> None:
        self._series: pd.Series | None = None
        self._is_fitted: bool = False
        self._fitted_values: pd.Series | None = None
        self._residual_std: float = 0.0

    @abstractmethod
    def fit(self, series: pd.Series) -> None:
        """Fit the model to a univariate monthly time series."""

    @abstractmethod
    def predict(self, horizon: int) -> StatisticalForecastResult:
        """Generate forecast with confidence intervals."""

    def in_sample_fitted(self) -> pd.Series:
        """Return in-sample fitted values for diagnostics."""
        if not self._is_fitted or self._fitted_values is None:
            raise RuntimeError("Model must be fitted before accessing fitted values")
        return self._fitted_values

    def _store_fit(self, series: pd.Series, fitted: pd.Series) -> None:
        """Common post-fit bookkeeping."""
        self._series = series.copy()
        self._fitted_values = fitted
        residuals = series - fitted.reindex(series.index)
        self._residual_std = float(residuals.std()) if len(residuals) > 1 else 0.0
        self._is_fitted = True

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def _next_periods(self, horizon: int) -> pd.DatetimeIndex:
        if self._series is None or self._series.empty:
            start = pd.Timestamp.today().normalize().replace(day=1)
        else:
            start = self._series.index[-1] + pd.offsets.MonthEnd(1)
        return pd.date_range(start=start, periods=horizon, freq="ME")
