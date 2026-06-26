"""
Forecast model registry and factory.

Centralises creation of all ``ForecastModel`` implementations and provides
auto-selection across statistical models.  Deterministic forecasting is
always available as a fallback.
"""

from __future__ import annotations

import pandas as pd

from financial_engine.forecasting.deterministic_forecast import DeterministicForecaster
from financial_engine.forecasting.interfaces import ForecastModel, ForecastModelType, ForecastOutput
from financial_engine.shared.dairy_model import DairyFarmAssumptions, MonthlyForecastResult
from financial_engine.statistics.diagnostics import ForecastDiagnostics
from financial_engine.statistics.model_selector import ModelSelector, create_model
from financial_engine.statistics.types import ForecastModelType as StatForecastModelType
from financial_engine.statistics.types import ModelComparisonResult, StatisticalForecastResult


# Map unified types to statistical sub-types (exclude deterministic + ML stubs)
_STAT_TYPE_MAP: dict[ForecastModelType, StatForecastModelType] = {
    ForecastModelType.LINEAR_TREND: StatForecastModelType.LINEAR_TREND,
    ForecastModelType.MOVING_AVERAGE: StatForecastModelType.MOVING_AVERAGE,
    ForecastModelType.EXPONENTIAL_SMOOTHING: StatForecastModelType.EXPONENTIAL_SMOOTHING,
    ForecastModelType.HOLT: StatForecastModelType.HOLT,
    ForecastModelType.ARIMA: StatForecastModelType.ARIMA,
}


class DeterministicForecastAdapter(ForecastModel):
    """Adapts Phase 1 ``DeterministicForecaster`` to ``ForecastModel``."""

    def __init__(self, assumptions: DairyFarmAssumptions | None = None) -> None:
        self._forecaster = DeterministicForecaster(assumptions)
        self._is_fitted = True

    @property
    def model_type(self) -> ForecastModelType:
        return ForecastModelType.DETERMINISTIC

    @property
    def model_name(self) -> str:
        return "deterministic"

    def fit(self, data: pd.Series | pd.DataFrame | None = None) -> None:
        if isinstance(data, pd.DataFrame):
            self._forecaster.fit(data)
        self._is_fitted = True

    def predict(self, horizon: int) -> ForecastOutput:
        result = self._forecaster.predict(horizon=horizon)
        detail: MonthlyForecastResult = result.detailed  # type: ignore[assignment]
        return ForecastOutput(
            periods=detail.periods,
            point_forecast=detail.monthly_profit,
            model_name=self.model_name,
            model_type=self.model_type,
            deterministic_detail=detail,
            metadata=result.metadata,
        )


class StatisticalForecastAdapter(ForecastModel):
    """Adapts Phase 2 ``StatisticalModel`` subclasses to ``ForecastModel``."""

    def __init__(self, model_type: ForecastModelType) -> None:
        stat_type = _STAT_TYPE_MAP[model_type]
        self._model = create_model(stat_type)
        self._model_type = model_type
        self._is_fitted = False

    @property
    def model_type(self) -> ForecastModelType:
        return self._model_type

    @property
    def model_name(self) -> str:
        return self._model.model_name

    def fit(self, data: pd.Series | pd.DataFrame | None = None) -> None:
        if data is None:
            raise ValueError("Statistical models require a historical series")
        series = data.iloc[:, 0] if isinstance(data, pd.DataFrame) else data
        self._model.fit(series.astype(float))
        self._is_fitted = True

    def predict(self, horizon: int) -> ForecastOutput:
        result: StatisticalForecastResult = self._model.predict(horizon)
        return _statistical_to_output(result, self._model_type)


def _statistical_to_output(
    result: StatisticalForecastResult,
    model_type: ForecastModelType,
) -> ForecastOutput:
    """Convert ``StatisticalForecastResult`` to unified ``ForecastOutput``."""
    return ForecastOutput(
        periods=result.periods,
        point_forecast=result.forecast,
        model_name=result.model_name,
        model_type=model_type,
        lower_confidence_95=result.lower_confidence_95,
        upper_confidence_95=result.upper_confidence_95,
        lower_prediction_95=result.lower_prediction_95,
        upper_prediction_95=result.upper_prediction_95,
        uncertainty=result.uncertainty,
        diagnostics=result.diagnostics,
        statistical_detail=result,
        metadata=result.metadata,
    )


def get_forecast_registry() -> dict[ForecastModelType, type[ForecastModel]]:
    """
    Return all **implemented** forecast model types.

    Phase 3 ML entries are intentionally omitted until implemented.
    """
    return {
        ForecastModelType.DETERMINISTIC: DeterministicForecastAdapter,
        ForecastModelType.LINEAR_TREND: lambda: StatisticalForecastAdapter(ForecastModelType.LINEAR_TREND),  # type: ignore[dict-item]
        ForecastModelType.MOVING_AVERAGE: lambda: StatisticalForecastAdapter(ForecastModelType.MOVING_AVERAGE),  # type: ignore[dict-item]
        ForecastModelType.EXPONENTIAL_SMOOTHING: lambda: StatisticalForecastAdapter(ForecastModelType.EXPONENTIAL_SMOOTHING),  # type: ignore[dict-item]
        ForecastModelType.HOLT: lambda: StatisticalForecastAdapter(ForecastModelType.HOLT),  # type: ignore[dict-item]
        ForecastModelType.ARIMA: lambda: StatisticalForecastAdapter(ForecastModelType.ARIMA),  # type: ignore[dict-item]
    }


def create_forecast_model(model_type: ForecastModelType, assumptions: DairyFarmAssumptions | None = None) -> ForecastModel:
    """Factory for unified forecast models."""
    if model_type == ForecastModelType.DETERMINISTIC:
        return DeterministicForecastAdapter(assumptions)
    if model_type in _STAT_TYPE_MAP:
        return StatisticalForecastAdapter(model_type)
    raise NotImplementedError(
        f"Model '{model_type.value}' is not yet implemented. "
        "Phase 3 ML models will plug in via MLForecastModel."
    )


class ForecastModelSelector:
    """
    Auto-selects the best statistical model and returns unified output.

    Wraps ``ModelSelector`` while exposing the ``ForecastModel`` interface.
    """

    def __init__(self, holdout_months: int = 3) -> None:
        self._selector = ModelSelector(holdout_months=holdout_months)

    def select_and_forecast(
        self,
        series: pd.Series,
        horizon: int,
        model_type: ForecastModelType = ForecastModelType.AUTO,
        target_column: str = "target",
    ) -> tuple[ForecastOutput, ModelComparisonResult]:
        stat_type = (
            _STAT_TYPE_MAP[model_type]
            if model_type != ForecastModelType.AUTO
            else StatForecastModelType.AUTO
        )
        result, comparison = self._selector.select_and_forecast(
            series, horizon=horizon, model_type=stat_type, target_column=target_column
        )
        unified_type = ForecastModelType(result.model_type.value)
        return _statistical_to_output(result, unified_type), comparison
