"""
Random Forest regression for farm financial prediction.

This module will eventually contain:
- Feature engineering from farm accounts and operational data
- Hyperparameter tuning via cross-validation
- Feature importance extraction for advisor explainability
- Out-of-sample evaluation and model persistence
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MLPredictionResult:
    """Output from a machine learning prediction."""

    predictions: np.ndarray
    feature_importances: dict[str, float]
    model_name: str


class RandomForestPredictor:
    """
    Scikit-learn Random Forest wrapper for farm outcome prediction.

    Future responsibilities:
    - Train on historical farm panels with mixed feature types
    - Handle missing values and categorical encodings
    - Export feature importances to the advisor module
    """

    def __init__(self, n_estimators: int = 100, random_state: int | None = 42) -> None:
        self.n_estimators = n_estimators
        self.random_state = random_state
        self._is_fitted: bool = False

    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        """Placeholder fit; full sklearn integration in a future iteration."""
        if features.empty:
            raise ValueError("Feature matrix must not be empty")
        self._is_fitted = True

    def predict(self, features: pd.DataFrame) -> MLPredictionResult:
        """Return zero predictions until the model is trained."""
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before prediction")
        predictions = np.zeros(len(features))
        return MLPredictionResult(
            predictions=predictions,
            feature_importances={},
            model_name="random_forest_placeholder",
        )
