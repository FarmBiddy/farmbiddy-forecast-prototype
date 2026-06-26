"""
Data loading and normalisation for financial intelligence pipelines.

Phase 2: supports importing historical monthly farm data with automatic
column mapping and missing-value handling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from financial_engine.shared.historical_data import FarmHistoricalData


class DataLoader:
    """
    Entry point for loading and preparing input data.

    Phase 1: CSV loading from the data directory.
    Phase 2: ``load_farm_history`` for statistical forecasting input.
    """

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)

    def load_csv(self, filename: str, **read_kwargs: Any) -> pd.DataFrame:
        """
        Load a CSV file from the configured data directory.

        Args:
            filename: Name of the file relative to data_dir.
            **read_kwargs: Additional arguments passed to pandas.read_csv.

        Returns:
            Raw DataFrame.

        Raises:
            FileNotFoundError: If the requested file does not exist.
        """
        path = self.data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {path}")
        return pd.read_csv(path, **read_kwargs)

    def load_farm_history(
        self,
        filename: str,
        farm_id: str = "default",
        fill_method: str = "interpolate",
        **read_kwargs: Any,
    ) -> FarmHistoricalData:
        """
        Load and normalise historical monthly farm data.

        Supported columns: milk_production, milk_price, feed_costs,
        labour_costs, operating_costs, debt, cash_balance, monthly_profit.

        Missing values are handled automatically.
        """
        df = self.load_csv(filename, **read_kwargs)
        return FarmHistoricalData.from_dataframe(
            df, farm_id=farm_id, fill_method=fill_method
        )

    def list_available_files(self) -> list[Path]:
        """Return paths to files in the data directory."""
        if not self.data_dir.exists():
            return []
        return sorted(self.data_dir.glob("*"))
