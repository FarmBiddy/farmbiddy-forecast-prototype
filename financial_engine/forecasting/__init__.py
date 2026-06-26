"""Forecasting package — deterministic and unified model interfaces."""

from financial_engine.forecasting.cashflow_projection import CashflowProjection, CashflowProjector
from financial_engine.forecasting.deterministic_forecast import (
    BaseForecaster,
    DeterministicForecaster,
    ForecastResult,
)
from financial_engine.forecasting.interfaces import (
    ForecastModel,
    ForecastModelType,
    ForecastOutput,
    MLForecastModel,
)
from financial_engine.forecasting.registry import (
    DeterministicForecastAdapter,
    ForecastModelSelector,
    create_forecast_model,
)
from financial_engine.forecasting.scenario_analysis import (
    ScenarioAnalyser,
    ScenarioComparison,
    ScenarioDefinition,
)

__all__ = [
    "BaseForecaster",
    "CashflowProjection",
    "CashflowProjector",
    "DeterministicForecastAdapter",
    "DeterministicForecaster",
    "ForecastModel",
    "ForecastModelSelector",
    "ForecastModelType",
    "ForecastOutput",
    "ForecastResult",
    "MLForecastModel",
    "ScenarioAnalyser",
    "ScenarioComparison",
    "ScenarioDefinition",
    "create_forecast_model",
]
