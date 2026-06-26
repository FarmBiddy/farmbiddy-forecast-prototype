"""
Facebook Prophet models for flexible time-series forecasting.

This module will eventually contain:
- Prophet integration for farm revenue with multiple seasonalities
- Holiday and event effects (e.g. scheme payment dates)
- Changepoint detection for structural shifts in farm performance
- Regressor support for external variables (commodity prices, weather)

Note: Prophet is an optional dependency; it will be added to requirements
when this module is implemented.
"""

from __future__ import annotations

import pandas as pd

from financial_engine.forecasting.deterministic_forecast import BaseForecaster, ForecastResult


class ProphetModel(BaseForecaster):
    """
    Prophet-based forecaster for complex seasonal farm financial data.

    Future responsibilities:
    - Configure yearly and monthly seasonality for agricultural cycles
    - Add custom regressors (milk price, fertiliser cost indices)
    - Return uncertainty intervals alongside point forecasts
    """

    def __init__(self, yearly_seasonality: bool = True, weekly_seasonality: bool = False) -> None:
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self._history: pd.DataFrame | None = None
        self._is_fitted: bool = False

    def fit(self, historical_data: pd.DataFrame) -> None:
        """
        Prepare Prophet-formatted history (ds, y columns).

        Full Prophet fitting will be implemented in a future iteration.
        """
        if historical_data.empty:
            raise ValueError("Historical data must not be empty")
        self._history = historical_data.copy()
        self._is_fitted = True

    def predict(self, horizon: int) -> ForecastResult:
        """Return a placeholder forecast until Prophet integration is complete."""
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before prediction")
        periods = pd.date_range(start=pd.Timestamp.today(), periods=horizon, freq="ME")
        values = pd.Series([0.0] * horizon, index=periods, name="prophet_forecast")
        return ForecastResult(
            periods=periods,
            values=values,
            model_name="prophet_placeholder",
            metadata={"yearly_seasonality": str(self.yearly_seasonality)},
        )
