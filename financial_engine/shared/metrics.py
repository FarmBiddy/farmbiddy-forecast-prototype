"""
Financial performance and forecast accuracy metrics.

This module will eventually contain:
- Profitability ratios (margin, ROI, break-even)
- Liquidity and solvency indicators
- Forecast error metrics (MAPE, RMSE, MAE)
- Benchmark comparisons against sector averages
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MetricResult:
    """Container for a computed financial metric."""

    name: str
    value: float
    unit: str = ""


class FinancialMetrics:
    """
    Calculator for standard financial and forecast evaluation metrics.

    Methods are placeholders; full implementations will be added per metric.
    """

    @staticmethod
    def gross_margin(revenue: pd.Series, costs: pd.Series) -> MetricResult:
        """
        Compute gross margin as (revenue - costs) / revenue.

        Args:
            revenue: Revenue time series or scalar series.
            costs: Direct cost time series aligned with revenue.

        Returns:
            MetricResult with margin expressed as a proportion.
        """
        total_revenue = revenue.sum()
        margin = (total_revenue - costs.sum()) / total_revenue if total_revenue else 0.0
        return MetricResult(name="gross_margin", value=float(margin), unit="ratio")

    @staticmethod
    def mean_absolute_percentage_error(
        actual: np.ndarray | pd.Series,
        predicted: np.ndarray | pd.Series,
    ) -> MetricResult:
        """
        Compute MAPE for forecast evaluation.

        Future: handle zero actuals and provide weighted variants.
        """
        actual_arr = np.asarray(actual, dtype=float)
        predicted_arr = np.asarray(predicted, dtype=float)
        mask = actual_arr != 0
        if not mask.any():
            return MetricResult(name="mape", value=float("nan"), unit="%")
        mape = np.mean(np.abs((actual_arr[mask] - predicted_arr[mask]) / actual_arr[mask])) * 100
        return MetricResult(name="mape", value=float(mape), unit="%")
