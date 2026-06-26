"""Holt's linear trend method (double exponential smoothing)."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from financial_engine.statistics.base import StatisticalModel
from financial_engine.statistics.diagnostics import compute_diagnostics
from financial_engine.statistics.intervals import build_intervals
from financial_engine.statistics.types import ForecastModelType, StatisticalForecastResult


class HoltTrendModel(StatisticalModel):
    """
    Holt's method with level and trend components.

    Captures farms with consistent upward or downward trajectories.
    """

    model_type = ForecastModelType.HOLT
    model_name = "holt"

    def __init__(self) -> None:
        super().__init__()
        self._level: float = 0.0
        self._trend: float = 0.0

    def fit(self, series: pd.Series) -> None:
        y = series.astype(float).dropna()
        if len(y) < 3:
            raise ValueError("Holt trend requires at least 3 observations")

        try:
            from statsmodels.tsa.holtwinters import Holt

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = Holt(y.values, initialization_method="estimated")
                result = model.fit(optimized=True)
            fitted = pd.Series(result.fittedvalues, index=y.index)
            future = result.forecast(2)
            self._level = float(future.iloc[0])
            self._trend = float(future.iloc[1] - future.iloc[0])
        except Exception:
            # Manual Holt fallback
            alpha, beta = 0.3, 0.1
            level = float(y.iloc[0])
            trend = float(y.iloc[1] - y.iloc[0])
            fitted_vals = []
            for val in y.values:
                prev_level = level
                level = alpha * val + (1 - alpha) * (level + trend)
                trend = beta * (level - prev_level) + (1 - beta) * trend
                fitted_vals.append(level)
            fitted = pd.Series(fitted_vals, index=y.index)
            self._level = level
            self._trend = trend

        self._store_fit(y, fitted)

    def predict(self, horizon: int) -> StatisticalForecastResult:
        if not self._is_fitted or self._series is None:
            raise RuntimeError("Model must be fitted before prediction")
        values = [self._level + self._trend * (h + 1) for h in range(horizon)]
        periods = self._next_periods(horizon)
        forecast, lci, uci, lpi, upi, unc = build_intervals(
            values, self._residual_std, len(self._series), index=periods
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
