"""
Phase 3 machine learning forecast interface.

Concrete ML models (Random Forest, XGBoost, LightGBM, Bayesian) will
implement ``MLForecastModel`` and register via ``register_ml_model()``.

DO NOT implement ML models here — architecture preparation only.
"""

from __future__ import annotations

from financial_engine.forecasting.interfaces import ForecastModelType, MLForecastModel

# Registry populated when Phase 3 models are implemented
_ML_REGISTRY: dict[ForecastModelType, type[MLForecastModel]] = {}


def register_ml_model(
    model_type: ForecastModelType,
    model_cls: type[MLForecastModel],
) -> None:
    """Register a Phase 3 ML forecaster into the unified model registry."""
    _ML_REGISTRY[model_type] = model_cls


def get_ml_registry() -> dict[ForecastModelType, type[MLForecastModel]]:
    """Return registered ML model classes (empty until Phase 3)."""
    return _ML_REGISTRY.copy()


def is_ml_model_available(model_type: ForecastModelType) -> bool:
    """Check whether a Phase 3 ML model has been registered."""
    return model_type in _ML_REGISTRY
