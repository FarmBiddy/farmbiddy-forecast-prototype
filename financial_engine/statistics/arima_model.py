"""
ARIMA forecasting using statsmodels.

Auto-selects among small (p,d,q) orders when not specified.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from financial_engine.statistics.base import StatisticalModel
from financial_engine.statistics.diagnostics import compute_diagnostics
from financial_engine.statistics.intervals import build_intervals
from financial_engine.statistics.types import ForecastModelType, StatisticalForecastResult


class ARIMAModel(StatisticalModel):
    """
    ARIMA model for autoregressive farm financial series.

    Phase 2 implementation — replaces the Phase 1 placeholder while
    keeping the same class name for import compatibility.
    """

    model_type = ForecastModelType.ARIMA
    model_name = "arima"

    DEFAULT_ORDERS = [(1, 1, 1), (1, 0, 1), (2, 1, 0), (0, 1, 1)]

    def __init__(self, order: tuple[int, int, int] | None = None) -> None:
        super().__init__()
        self.order = order
        self._forecast_values: np.ndarray | None = None
        self._arima_result = None

    def fit(self, series: pd.Series) -> None:
        y = series.astype(float).dropna()
        if len(y) < 4:
            raise ValueError("ARIMA requires at least 4 observations")

        from statsmodels.tsa.arima.model import ARIMA

        best_aic = np.inf
        best_result = None
        orders = [self.order] if self.order else self.DEFAULT_ORDERS

        for order in orders:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = ARIMA(y.values, order=order)
                    result = model.fit()
                if result.aic < best_aic:
                    best_aic = result.aic
                    best_result = result
            except Exception:
                continue

        if best_result is None:
            # Fallback to random walk (d=1, naive)
            fitted = y.shift(1).bfill()
            self._store_fit(y, fitted)
            self._forecast_values = np.full(12, float(y.iloc[-1]))
            return

        self._arima_result = best_result
        fitted = pd.Series(best_result.fittedvalues, index=y.index)
        self._store_fit(y, fitted)

    def predict(self, horizon: int) -> StatisticalForecastResult:
        if not self._is_fitted or self._series is None:
            raise RuntimeError("Model must be fitted before prediction")

        periods = self._next_periods(horizon)

        if self._arima_result is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fc = self._arima_result.get_forecast(steps=horizon)
            values = np.asarray(fc.predicted_mean, dtype=float)
            try:
                conf = fc.conf_int(alpha=0.05)
                if hasattr(conf, "iloc"):
                    lower_pi_arr = np.asarray(conf.iloc[:, 0], dtype=float)
                    upper_pi_arr = np.asarray(conf.iloc[:, 1], dtype=float)
                else:
                    lower_pi_arr = np.asarray(conf[:, 0], dtype=float)
                    upper_pi_arr = np.asarray(conf[:, 1], dtype=float)
            except Exception:
                return self._predict_fallback(horizon, periods)

            forecast = pd.Series(values, index=periods)
            lower_pi = pd.Series(lower_pi_arr, index=periods)
            upper_pi = pd.Series(upper_pi_arr, index=periods)
            unc = (upper_pi - lower_pi) / 2
            _, lower_ci, upper_ci, _, _, _ = build_intervals(
                values, self._residual_std, len(self._series), index=periods
            )
        else:
            return self._predict_fallback(horizon, periods)

        diagnostics = compute_diagnostics(self._series, self.in_sample_fitted())
        order_str = str(self._arima_result.model.order) if self._arima_result else "naive"
        return StatisticalForecastResult(
            periods=periods,
            forecast=forecast,
            lower_confidence_95=lower_ci,
            upper_confidence_95=upper_ci,
            lower_prediction_95=lower_pi,
            upper_prediction_95=upper_pi,
            uncertainty=unc,
            model_name=self.model_name,
            model_type=self.model_type,
            diagnostics=diagnostics,
            metadata={"order": order_str},
        )

    def _predict_fallback(
        self, horizon: int, periods: pd.DatetimeIndex
    ) -> StatisticalForecastResult:
        """Naive fallback when ARIMA intervals are unavailable."""
        values = [float(self._series.iloc[-1])] * horizon  # type: ignore[union-attr]
        forecast, lower_ci, upper_ci, lower_pi, upper_pi, unc = build_intervals(
            values, self._residual_std, len(self._series), index=periods  # type: ignore[arg-type]
        )
        diagnostics = compute_diagnostics(self._series, self.in_sample_fitted())  # type: ignore[arg-type]
        return StatisticalForecastResult(
            periods=periods,
            forecast=forecast,
            lower_confidence_95=lower_ci,
            upper_confidence_95=upper_ci,
            lower_prediction_95=lower_pi,
            upper_prediction_95=upper_pi,
            uncertainty=unc,
            model_name=self.model_name,
            model_type=self.model_type,
            diagnostics=diagnostics,
            metadata={"order": "naive"},
        )
