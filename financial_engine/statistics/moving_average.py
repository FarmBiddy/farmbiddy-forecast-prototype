"""Simple and weighted moving-average forecasting."""

from __future__ import annotations

import pandas as pd

from financial_engine.statistics.base import StatisticalModel
from financial_engine.statistics.diagnostics import compute_diagnostics
from financial_engine.statistics.intervals import build_intervals
from financial_engine.statistics.types import ForecastModelType, StatisticalForecastResult


class MovingAverageModel(StatisticalModel):
    """
    Rolling-mean forecaster — flat forecast equal to recent average.

    Robust baseline for stable monthly farm accounts.
    """

    model_type = ForecastModelType.MOVING_AVERAGE
    model_name = "moving_average"

    def __init__(self, window: int = 3) -> None:
        super().__init__()
        self.window = max(1, window)
        self._last_ma: float = 0.0

    def fit(self, series: pd.Series) -> None:
        y = series.astype(float).dropna()
        if len(y) < 1:
            raise ValueError("Moving average requires at least 1 observation")
        ma = y.rolling(window=min(self.window, len(y)), min_periods=1).mean()
        self._last_ma = float(ma.iloc[-1])
        self._store_fit(y, ma)

    def predict(self, horizon: int) -> StatisticalForecastResult:
        if not self._is_fitted or self._series is None:
            raise RuntimeError("Model must be fitted before prediction")
        values = [self._last_ma] * horizon
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
            metadata={"window": str(self.window)},
        )
