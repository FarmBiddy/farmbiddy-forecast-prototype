"""Classical time-series and statistical forecasting models (Phase 2)."""

from financial_engine.statistics.arima_model import ARIMAModel
from financial_engine.statistics.engine import StatisticalForecastEngine
from financial_engine.statistics.exponential_smoothing import ExponentialSmoothingModel
from financial_engine.statistics.holt_trend import HoltTrendModel
from financial_engine.statistics.linear_trend import LinearTrendModel
from financial_engine.statistics.model_selector import ModelSelector, create_model, get_model_registry
from financial_engine.statistics.moving_average import MovingAverageModel
from financial_engine.statistics.prophet_model import ProphetModel
from financial_engine.statistics.types import ForecastModelType, StatisticalForecastResult

__all__ = [
    "ARIMAModel",
    "ExponentialSmoothingModel",
    "ForecastModelType",
    "HoltTrendModel",
    "LinearTrendModel",
    "ModelSelector",
    "MovingAverageModel",
    "ProphetModel",
    "StatisticalForecastEngine",
    "StatisticalForecastResult",
    "create_model",
    "get_model_registry",
]
