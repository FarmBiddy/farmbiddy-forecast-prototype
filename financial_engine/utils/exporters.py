"""
Data export utilities for financial intelligence outputs.

This module will eventually contain:
- JSON and CSV export of forecasts, simulations, and advisory summaries
- Serialisation of Pydantic models for API handoff to FarmBiddy
- Batch export pipelines for research datasets
- Schema versioning for downstream integration
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


class DataExporter:
    """
    Exports engine outputs to files in the outputs directory.

    Future responsibilities:
    - Standardised export schemas for FarmBiddy integration
    - Incremental export for long-running simulation batches
    - Compression and archival of large Monte Carlo result sets
    """

    def __init__(self, output_dir: Path | str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_csv(self, df: pd.DataFrame, filename: str) -> Path:
        """Export a DataFrame to CSV."""
        path = self.output_dir / filename
        df.to_csv(path, index=True)
        return path

    def to_json(self, data: dict[str, Any], filename: str) -> Path:
        """Export a dictionary to JSON."""
        path = self.output_dir / filename
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return path

    def to_parquet(self, df: pd.DataFrame, filename: str) -> Path:
        """Export a DataFrame to Parquet for efficient storage."""
        path = self.output_dir / filename
        df.to_parquet(path, index=True)
        return path
