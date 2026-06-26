"""
Simple exponential smoothing (single-parameter level smoothing).

Uses statsmodels when available; falls back to a manual implementation.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from financial_engine.statistics.base import StatisticalModel
from financial_engine.statistics.diagnostics import compute_diagnostics
from financial_engine.statistics.intervals import build_intervals
from financial_engine.statistics.types import ForecastModelType, StatisticalForecastResult


class ExponentialSmoothingModel(StatisticalModel):
    """
    Single-parameter exponential smoothing for level-only series.

    Phase 2 implementation — replaces the Phase 1 placeholder.
    """

    model_type = ForecastModelType.EXPONENTIAL_SMOOTHING
    model_name = "exponential_smoothing"

    def __init__(self, alpha: float | None = None) -> None:
        super().__init__()
        self.alpha = alpha
        self._level: float = 0.0
        self._smoothed: pd.Series | None = None

    def fit(self, series: pd.Series) -> None:
        y = series.astype(float).dropna()
        if len(y) < 2:
            raise ValueError("Exponential smoothing requires at least 2 observations")

        try:
            from statsmodels.tsa.holtwinters import SimpleExpSmoothing

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = SimpleExpSmoothing(y.values, initialization_method="estimated")
                fit_kwargs: dict = {}
                if self.alpha is not None:
                    fit_kwargs["smoothing_level"] = self.alpha
                result = model.fit(optimized=self.alpha is None, **fit_kwargs)
            fitted = pd.Series(result.fittedvalues, index=y.index)
            self._level = float(result.forecast(1)[0])
        except Exception:
            # Manual fallback
            alpha = self.alpha if self.alpha is not None else 0.3
            level = float(y.iloc[0])
            smoothed_vals = []
            for val in y.values:
                level = alpha * val + (1 - alpha) * level
                smoothed_vals.append(level)
            fitted = pd.Series(smoothed_vals, index=y.index)
            self._level = level

        self._smoothed = fitted
        self._store_fit(y, fitted)

    def predict(self, horizon: int) -> StatisticalForecastResult:
        if not self._is_fitted or self._series is None:
            raise RuntimeError("Model must be fitted before prediction")
        values = [self._level] * horizon
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
