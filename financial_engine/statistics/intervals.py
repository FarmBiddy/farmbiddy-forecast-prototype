"""
Confidence and prediction interval helpers for statistical forecasts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def build_intervals(
    forecast: np.ndarray | pd.Series,
    residual_std: float,
    n_train: int,
    confidence: float = 0.95,
    index: pd.DatetimeIndex | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Build confidence and prediction intervals from residual standard error.

    Confidence interval → uncertainty of the mean forecast.
    Prediction interval → uncertainty of individual future observations.
    """
    z = float(stats.norm.ppf(0.5 + confidence / 2))
    forecast_arr = np.asarray(forecast, dtype=float)
    horizon = len(forecast_arr)

    if index is None:
        index = pd.date_range(start=pd.Timestamp.today(), periods=horizon, freq="ME")

    # Widening uncertainty over forecast horizon
    uncertainty = np.array(
        [residual_std * np.sqrt(1 + (h + 1) / max(n_train, 1)) for h in range(horizon)]
    )
    ci_half = z * residual_std / np.sqrt(max(n_train, 1))

    forecast_s = pd.Series(forecast_arr, index=index, name="forecast")
    lower_ci = pd.Series(forecast_arr - ci_half, index=index)
    upper_ci = pd.Series(forecast_arr + ci_half, index=index)
    lower_pi = pd.Series(forecast_arr - z * uncertainty, index=index)
    upper_pi = pd.Series(forecast_arr + z * uncertainty, index=index)
    uncertainty_s = pd.Series(uncertainty, index=index, name="uncertainty")

    return forecast_s, lower_ci, upper_ci, lower_pi, upper_pi, uncertainty_s
