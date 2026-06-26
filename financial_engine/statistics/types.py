"""
Shared types for Phase 2 statistical forecasting.

All statistical models return ``StatisticalForecastResult`` so the pipeline,
dashboard, and diagnostics layers work identically regardless of model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class ForecastModelType(str, Enum):
    """Selectable forecasting model (Phase 2)."""

    AUTO = "auto"
    LINEAR_TREND = "linear_trend"
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    HOLT = "holt"
    ARIMA = "arima"


@dataclass
class ForecastDiagnostics:
    """In-sample and hold-out forecast accuracy metrics."""

    rmse: float
    mae: float
    mape: float
    bias: float
    residuals: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    n_observations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rmse": round(self.rmse, 4),
            "mae": round(self.mae, 4),
            "mape": round(self.mape, 4),
            "bias": round(self.bias, 4),
            "n_observations": self.n_observations,
            "residual_summary": {
                "mean": round(float(self.residuals.mean()), 4) if len(self.residuals) else 0,
                "std": round(float(self.residuals.std()), 4) if len(self.residuals) else 0,
            },
        }


@dataclass
class StatisticalForecastResult:
    """
    Forecast output with 95 % confidence and prediction intervals.

    Compatible with dashboard JSON and future Phase 3 ensemble methods.
    """

    periods: pd.DatetimeIndex
    forecast: pd.Series
    lower_confidence_95: pd.Series
    upper_confidence_95: pd.Series
    lower_prediction_95: pd.Series
    upper_prediction_95: pd.Series
    uncertainty: pd.Series
    model_name: str
    model_type: ForecastModelType
    diagnostics: ForecastDiagnostics
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def values(self) -> pd.Series:
        """Alias for compatibility with Phase 1 ``ForecastResult.values``."""
        return self.forecast

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_type": self.model_type.value,
            "diagnostics": self.diagnostics.to_dict(),
            "metadata": self.metadata,
            "summary": {
                "horizon": len(self.periods),
                "mean_forecast": round(float(self.forecast.mean()), 2),
                "total_forecast": round(float(self.forecast.sum()), 2),
                "mean_uncertainty": round(float(self.uncertainty.mean()), 2),
            },
            "periods": [str(p.date()) for p in self.periods],
            "forecast": {str(p.date()): round(v, 2) for p, v in self.forecast.items()},
            "confidence_band_95": {
                "lower": {str(p.date()): round(v, 2) for p, v in self.lower_confidence_95.items()},
                "upper": {str(p.date()): round(v, 2) for p, v in self.upper_confidence_95.items()},
            },
            "prediction_interval_95": {
                "lower": {str(p.date()): round(v, 2) for p, v in self.lower_prediction_95.items()},
                "upper": {str(p.date()): round(v, 2) for p, v in self.upper_prediction_95.items()},
            },
            "uncertainty": {str(p.date()): round(v, 2) for p, v in self.uncertainty.items()},
        }


@dataclass
class ModelComparisonEntry:
    """Single model evaluated during auto-selection."""

    model_type: ForecastModelType
    model_name: str
    rmse: float
    mae: float
    mape: float
    combined_score: float
    is_selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type.value,
            "model_name": self.model_name,
            "rmse": round(self.rmse, 4),
            "mae": round(self.mae, 4),
            "mape": round(self.mape, 4),
            "combined_score": round(self.combined_score, 4),
            "is_selected": self.is_selected,
        }


@dataclass
class ModelComparisonResult:
    """Result of comparing all statistical models."""

    entries: list[ModelComparisonEntry]
    recommended_model: ForecastModelType
    target_column: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_column": self.target_column,
            "recommended_model": self.recommended_model.value,
            "models": [e.to_dict() for e in self.entries],
        }
