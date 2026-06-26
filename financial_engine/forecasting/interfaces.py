"""
Unified forecasting interface for the FarmBiddy Financial Intelligence Engine.

All forecast implementations — deterministic, statistical, and future ML models —
implement ``ForecastModel`` so the pipeline, dashboard, and model selector
can treat them uniformly without changing downstream consumers.

Phase 3 ML models (Random Forest, XGBoost, LightGBM, Bayesian) will subclass
``MLForecastModel`` which extends this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from financial_engine.statistics.diagnostics import ForecastDiagnostics
from financial_engine.statistics.types import StatisticalForecastResult


class ForecastModelType(str, Enum):
    """All supported forecasting model identifiers."""

    AUTO = "auto"
    DETERMINISTIC = "deterministic"
    LINEAR_TREND = "linear_trend"
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    HOLT = "holt"
    ARIMA = "arima"
    # Phase 3 placeholders — not yet implemented
    RANDOM_FOREST = "random_forest"
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    BAYESIAN = "bayesian"


@dataclass
class ForecastOutput:
    """
    Unified forecast result consumed by dashboard, explainability, and API layers.

    Wraps either a deterministic ``MonthlyForecastResult`` or a statistical
    ``StatisticalForecastResult``.
    """

    periods: pd.DatetimeIndex
    point_forecast: pd.Series
    model_name: str
    model_type: ForecastModelType
    lower_confidence_95: pd.Series | None = None
    upper_confidence_95: pd.Series | None = None
    lower_prediction_95: pd.Series | None = None
    upper_prediction_95: pd.Series | None = None
    uncertainty: pd.Series | None = None
    diagnostics: ForecastDiagnostics | None = None
    deterministic_detail: Any | None = None
    statistical_detail: StatisticalForecastResult | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def has_intervals(self) -> bool:
        return self.lower_prediction_95 is not None and self.upper_prediction_95 is not None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model_name": self.model_name,
            "model_type": self.model_type.value,
            "periods": [str(p.date()) for p in self.periods],
            "point_forecast": {
                str(p.date()): round(v, 2) for p, v in self.point_forecast.items()
            },
            "metadata": self.metadata,
        }
        if self.diagnostics:
            payload["diagnostics"] = self.diagnostics.to_dict()
        if self.has_intervals and self.lower_prediction_95 is not None:
            payload["confidence_band_95"] = {
                "lower": {str(p.date()): round(v, 2) for p, v in self.lower_confidence_95.items()}
                if self.lower_confidence_95 is not None
                else {},
                "upper": {str(p.date()): round(v, 2) for p, v in self.upper_confidence_95.items()}
                if self.upper_confidence_95 is not None
                else {},
            }
            payload["prediction_interval_95"] = {
                "lower": {str(p.date()): round(v, 2) for p, v in self.lower_prediction_95.items()},
                "upper": {str(p.date()): round(v, 2) for p, v in self.upper_prediction_95.items()},
            }
        return payload


class ForecastModel(ABC):
    """
    Common interface for every forecasting implementation.

    Subclasses must implement ``fit`` and ``predict``.  The pipeline and
    model registry depend only on this contract.
    """

    @property
    @abstractmethod
    def model_type(self) -> ForecastModelType:
        """Unique model identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model name."""

    @abstractmethod
    def fit(self, data: pd.Series | pd.DataFrame | None = None) -> None:
        """Train or configure the model on historical observations."""

    @abstractmethod
    def predict(self, horizon: int) -> ForecastOutput:
        """Generate a forecast for the given horizon."""

    def is_fitted(self) -> bool:
        """Return whether the model has been configured."""
        return getattr(self, "_is_fitted", False)


class MLForecastModel(ForecastModel):
    """
    Extension point for Phase 3 machine-learning forecasters.

    ML models will implement ``fit(features, target)`` semantics via the
    ``data`` parameter and return ``ForecastOutput`` with SHAP metadata
    in ``metadata`` for the explainability engine.

    DO NOT implement concrete ML models here — only the contract.
    """

    @abstractmethod
    def feature_importances(self) -> dict[str, float]:
        """Return feature importance scores for explainability."""

    @abstractmethod
    def supports_probabilistic_output(self) -> bool:
        """Whether the model can produce prediction intervals."""
