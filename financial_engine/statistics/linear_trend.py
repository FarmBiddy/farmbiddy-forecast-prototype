"""Linear trend (OLS on time index) forecasting."""

from __future__ import annotations

import numpy as np
import pandas as pd

from financial_engine.statistics.base import StatisticalModel
from financial_engine.statistics.diagnostics import compute_diagnostics
from financial_engine.statistics.intervals import build_intervals
from financial_engine.statistics.types import ForecastModelType, StatisticalForecastResult


class LinearTrendModel(StatisticalModel):
    """
    Fits a straight-line trend over time.

    Suitable when farm metrics show steady growth or decline.
    """

    model_type = ForecastModelType.LINEAR_TREND
    model_name = "linear_trend"

    def __init__(self) -> None:
        super().__init__()
        self._slope: float = 0.0
        self._intercept: float = 0.0

    def fit(self, series: pd.Series) -> None:
        y = series.astype(float).dropna()
        if len(y) < 2:
            raise ValueError("Linear trend requires at least 2 observations")
        x = np.arange(len(y), dtype=float)
        coeffs = np.polyfit(x, y.values, 1)
        self._slope, self._intercept = float(coeffs[0]), float(coeffs[1])
        fitted = pd.Series(self._intercept + self._slope * x, index=y.index)
        self._store_fit(y, fitted)

    def predict(self, horizon: int) -> StatisticalForecastResult:
        if not self._is_fitted or self._series is None:
            raise RuntimeError("Model must be fitted before prediction")
        n = len(self._series)
        future_x = np.arange(n, n + horizon, dtype=float)
        values = self._intercept + self._slope * future_x
        periods = self._next_periods(horizon)
        forecast, lci, uci, lpi, upi, unc = build_intervals(
            values, self._residual_std, n, index=periods
        )
        diagnostics = compute_diagnostics(self._series, self.in_sample_fitted())
        return StatisticalForecastResult(
            periods=periods,
            forecast=forecast,
            lower_confidence_95=lci,
            upper_confidence_95=uci,
            lower_prediction_95=lpi,
            upper_prediction_95=upi,
            uncertainty=unc,
            model_name=self.model_name,
            model_type=self.model_type,
            diagnostics=diagnostics,
        )
