"""
Automatic model selection by comparing RMSE and MAE on hold-out data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from financial_engine.statistics.arima_model import ARIMAModel
from financial_engine.statistics.base import StatisticalModel
from financial_engine.statistics.diagnostics import compute_diagnostics
from financial_engine.statistics.exponential_smoothing import ExponentialSmoothingModel
from financial_engine.statistics.holt_trend import HoltTrendModel
from financial_engine.statistics.linear_trend import LinearTrendModel
from financial_engine.statistics.moving_average import MovingAverageModel
from financial_engine.statistics.types import (
    ForecastModelType,
    ModelComparisonEntry,
    ModelComparisonResult,
    StatisticalForecastResult,
)


def get_model_registry() -> dict[ForecastModelType, type[StatisticalModel]]:
    """Return all available Phase 2 statistical models."""
    return {
        ForecastModelType.LINEAR_TREND: LinearTrendModel,
        ForecastModelType.MOVING_AVERAGE: MovingAverageModel,
        ForecastModelType.EXPONENTIAL_SMOOTHING: ExponentialSmoothingModel,
        ForecastModelType.HOLT: HoltTrendModel,
        ForecastModelType.ARIMA: ARIMAModel,
    }


def create_model(model_type: ForecastModelType) -> StatisticalModel:
    """Factory for statistical forecast models."""
    registry = get_model_registry()
    if model_type not in registry:
        raise ValueError(f"Unknown model type: {model_type}")
    return registry[model_type]()


class ModelSelector:
    """
    Compares all statistical models and recommends the best performer.

    Uses a temporal hold-out set (last ``holdout_months``) for evaluation.
    Selection criterion: lowest normalised RMSE + MAE combined score.
    """

    def __init__(self, holdout_months: int = 3) -> None:
        self.holdout_months = max(1, holdout_months)

    def _evaluate_model(
        self,
        model_type: ForecastModelType,
        train: pd.Series,
        test: pd.Series,
    ) -> ModelComparisonEntry | None:
        try:
            model = create_model(model_type)
            model.fit(train)
            result = model.predict(len(test))
            predicted = result.forecast.values
            actual = test.values
            diag = compute_diagnostics(
                pd.Series(actual, index=test.index),
                pd.Series(predicted, index=test.index),
            )
            combined = diag.rmse + diag.mae
            return ModelComparisonEntry(
                model_type=model_type,
                model_name=model.model_name,
                rmse=diag.rmse,
                mae=diag.mae,
                mape=diag.mape,
                combined_score=combined,
            )
        except Exception:
            return None

    def compare(
        self,
        series: pd.Series,
        target_column: str = "target",
    ) -> ModelComparisonResult:
        """Evaluate every model and rank by hold-out performance."""
        y = series.astype(float).dropna()
        holdout = min(self.holdout_months, max(1, len(y) // 4))
        if len(y) <= holdout + 2:
            holdout = max(1, len(y) // 3)

        train = y.iloc[:-holdout]
        test = y.iloc[-holdout:]

        entries: list[ModelComparisonEntry] = []
        for model_type in get_model_registry():
            entry = self._evaluate_model(model_type, train, test)
            if entry is not None:
                entries.append(entry)

        if not entries:
            recommended = ForecastModelType.LINEAR_TREND
        else:
            entries.sort(key=lambda e: e.combined_score)
            recommended = entries[0].model_type
            entries[0].is_selected = True

        return ModelComparisonResult(
            entries=entries,
            recommended_model=recommended,
            target_column=target_column,
        )

    def select_and_forecast(
        self,
        series: pd.Series,
        horizon: int,
        model_type: ForecastModelType = ForecastModelType.AUTO,
        target_column: str = "target",
    ) -> tuple[StatisticalForecastResult, ModelComparisonResult]:
        """
        Select model (auto or manual) and produce final forecast on full data.
        """
        comparison = self.compare(series, target_column=target_column)

        selected = (
            comparison.recommended_model
            if model_type == ForecastModelType.AUTO
            else model_type
        )

        model = create_model(selected)
        model.fit(series.astype(float).dropna())
        forecast = model.predict(horizon)

        # Mark selected in comparison
        for entry in comparison.entries:
            entry.is_selected = entry.model_type == selected

        forecast.metadata["selection_mode"] = model_type.value
        forecast.metadata["recommended_model"] = comparison.recommended_model.value
        return forecast, comparison
