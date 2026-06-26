"""
Forecast diagnostics — RMSE, MAE, MAPE, bias, and residual analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from financial_engine.statistics.types import ForecastDiagnostics


def compute_diagnostics(
    actual: pd.Series,
    predicted: pd.Series,
) -> ForecastDiagnostics:
    """
    Compute standard forecast accuracy metrics and residuals.

    Args:
        actual: Observed values aligned with ``predicted``.
        predicted: Model fitted or hold-out predictions.

    Returns:
        ``ForecastDiagnostics`` with residuals for further analysis.
    """
    aligned = pd.concat([actual, predicted], axis=1, join="inner").dropna()
    if aligned.empty:
        return ForecastDiagnostics(
            rmse=0.0, mae=0.0, mape=0.0, bias=0.0, n_observations=0
        )

    y = aligned.iloc[:, 0].astype(float)
    yhat = aligned.iloc[:, 1].astype(float)
    residuals = y - yhat

    rmse = float(np.sqrt(np.mean(residuals**2)))
    mae = float(np.mean(np.abs(residuals)))
    mask = y != 0
    mape = (
        float(np.mean(np.abs(residuals[mask] / y[mask])) * 100)
        if mask.any()
        else 0.0
    )
    bias = float(np.mean(residuals))

    return ForecastDiagnostics(
        rmse=rmse,
        mae=mae,
        mape=mape,
        bias=bias,
        residuals=residuals,
        n_observations=len(aligned),
    )


def residual_analysis(diagnostics: ForecastDiagnostics) -> dict[str, float]:
    """Summarise residual distribution for reporting."""
    r = diagnostics.residuals
    if len(r) == 0:
        return {"count": 0}
    return {
        "count": len(r),
        "mean": float(r.mean()),
        "std": float(r.std()),
        "min": float(r.min()),
        "max": float(r.max()),
        "skew": float(r.skew()) if len(r) > 2 else 0.0,
    }
