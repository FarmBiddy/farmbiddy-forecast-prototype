"""
Historical data preprocessing utilities.

Prepares raw farm datasets for forecasting, simulation, and API ingestion.
Handles resampling, outlier clipping, missing values, and horizon alignment.
"""

from __future__ import annotations

import pandas as pd

from financial_engine.shared.historical_data import FarmHistoricalData


class HistoricalDataPreprocessor:
    """
    Transforms raw historical farm data into analysis-ready time series.

    Designed for reuse by the statistical engine, future FastAPI upload
    endpoints, and batch import pipelines.
    """

    def __init__(
        self,
        data: FarmHistoricalData,
        fill_method: str = "interpolate",
        clip_outliers_std: float | None = 3.0,
    ) -> None:
        self.data = data
        self.fill_method = fill_method
        self.clip_outliers_std = clip_outliers_std

    def to_dataframe(self) -> pd.DataFrame:
        """Return cleaned monthly DataFrame."""
        df = self.data.to_dataframe()
        if self.clip_outliers_std is not None:
            df = self._clip_outliers(df)
        return df

    def get_series(self, column: str) -> pd.Series:
        """Return a preprocessed series for the given column."""
        return self.data.get_series(column)

    def resample_monthly(self, column: str) -> pd.Series:
        """Ensure monthly frequency with end-of-month timestamps."""
        series = self.get_series(column)
        return series.resample("ME").mean().interpolate().ffill()

    def prepare_for_horizon(self, column: str, min_observations: int = 6) -> pd.Series:
        """
        Validate and return a series suitable for forecasting.

        Raises:
            ValueError: If insufficient history for the requested analysis.
        """
        series = self.get_series(column).dropna()
        if len(series) < min_observations:
            raise ValueError(
                f"Insufficient history for '{column}': "
                f"{len(series)} observations (minimum {min_observations})"
            )
        return series

    def summary(self) -> dict[str, object]:
        """Return dataset summary statistics for dashboard/API."""
        df = self.to_dataframe()
        numeric = df.select_dtypes(include="number")
        return {
            "farm_id": self.data.farm_id,
            "periods": len(df),
            "columns": list(df.columns),
            "date_range": {
                "start": str(df.index.min().date()) if len(df) else None,
                "end": str(df.index.max().date()) if len(df) else None,
            },
            "missing_filled": self.fill_method,
            "column_stats": {
                col: {
                    "mean": round(float(numeric[col].mean()), 2),
                    "std": round(float(numeric[col].std()), 2),
                    "min": round(float(numeric[col].min()), 2),
                    "max": round(float(numeric[col].max()), 2),
                }
                for col in numeric.columns
            },
        }

    def _clip_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Winsorise numeric columns beyond N standard deviations."""
        numeric_cols = df.select_dtypes(include="number").columns
        clipped = df.copy()
        for col in numeric_cols:
            mean = clipped[col].mean()
            std = clipped[col].std()
            if std == 0 or pd.isna(std):
                continue
            lower = mean - self.clip_outliers_std * std
            upper = mean + self.clip_outliers_std * std
            clipped[col] = clipped[col].clip(lower, upper)
        return clipped
