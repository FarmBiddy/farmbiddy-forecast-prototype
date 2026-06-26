"""Machine learning models for prediction and pattern discovery (Phase 3 stubs)."""

from financial_engine.machine_learning.clustering import FarmClusterAnalyser
from financial_engine.machine_learning.forecast_interface import (
    get_ml_registry,
    is_ml_model_available,
    register_ml_model,
)
from financial_engine.machine_learning.random_forest_model import RandomForestPredictor
from financial_engine.machine_learning.xgboost_model import XGBoostPredictor

__all__ = [
    "FarmClusterAnalyser",
    "RandomForestPredictor",
    "XGBoostPredictor",
    "get_ml_registry",
    "is_ml_model_available",
    "register_ml_model",
]
