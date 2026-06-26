"""
Historical monthly farm data schema and preprocessing.

Handles missing values via interpolation and forward-fill so statistical
models receive clean monthly series.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

# Standard column names (aliases mapped during import)
STANDARD_COLUMNS = [
    "date",
    "milk_production",
    "milk_price",
    "feed_costs",
    "labour_costs",
    "operating_costs",
    "debt",
    "cash_balance",
    "monthly_profit",
]

COLUMN_ALIASES: dict[str, str] = {
    "period": "date",
    "month": "date",
    "milk_litres": "milk_production",
    "milk_volume": "milk_production",
    "production": "milk_production",
    "price": "milk_price",
    "feed": "feed_costs",
    "feed_cost": "feed_costs",
    "labour": "labour_costs",
    "labor_costs": "labour_costs",
    "operating": "operating_costs",
    "total_debt": "debt",
    "cash": "cash_balance",
    "profit": "monthly_profit",
    "net_profit": "monthly_profit",
}


class FarmHistoricalData(BaseModel):
    """
    Validated historical monthly records for a dairy farm.

    Missing numeric values are filled automatically on ``to_dataframe()``.
    """

    records: list[dict[str, Any]] = Field(default_factory=list)
    farm_id: str = Field(default="default")
    fill_method: str = Field(
        default="interpolate",
        description="interpolate | ffill | bfill",
    )

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, **kwargs: Any) -> FarmHistoricalData:
        """Create from a DataFrame with normalised column names."""
        normalised = cls._normalise_columns(df.copy())
        if "date" in normalised.columns:
            normalised["date"] = pd.to_datetime(normalised["date"])
        records = normalised.to_dict(orient="records")
        return cls(records=records, **kwargs)

    @staticmethod
    def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        rename = {c: COLUMN_ALIASES[c] for c in df.columns if c in COLUMN_ALIASES}
        return df.rename(columns=rename)

    def to_dataframe(self) -> pd.DataFrame:
        """Return a cleaned DataFrame with missing values handled."""
        if not self.records:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        df = pd.DataFrame(self.records)
        df = self._normalise_columns(df)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").set_index("date")
        else:
            df.index = pd.date_range(
                end=pd.Timestamp.today(), periods=len(df), freq="ME"
            )

        numeric_cols = [c for c in df.columns if c != "date"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = self._fill_missing(df, numeric_cols)
        return df

    def _fill_missing(self, df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        for col in columns:
            if col not in df.columns:
                continue
            if self.fill_method == "ffill":
                df[col] = df[col].ffill().bfill()
            elif self.fill_method == "bfill":
                df[col] = df[col].bfill().ffill()
            else:
                df[col] = df[col].interpolate(method="linear").ffill().bfill()
        return df

    def numeric_columns(self) -> list[str]:
        df = self.to_dataframe()
        return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    def get_series(self, column: str) -> pd.Series:
        df = self.to_dataframe()
        if column == "monthly_profit" and (
            column not in df.columns or df[column].isna().all()
        ):
            return self.derive_monthly_profit()
        if column not in df.columns:
            raise KeyError(
                f"Column '{column}' not found. Available: {list(df.columns)}"
            )
        return df[column].astype(float)

    def derive_monthly_profit(self) -> pd.Series:
        """
        Derive monthly profit from components when not supplied directly.

        profit ≈ milk_production × milk_price − feed − labour − operating
        """
        df = self.to_dataframe()
        if "monthly_profit" in df.columns and df["monthly_profit"].notna().any():
            return df["monthly_profit"].astype(float)

        revenue = pd.Series(0.0, index=df.index)
        if "milk_production" in df.columns and "milk_price" in df.columns:
            revenue = df["milk_production"] * df["milk_price"]

        costs = pd.Series(0.0, index=df.index)
        for col in ("feed_costs", "labour_costs", "operating_costs"):
            if col in df.columns:
                costs = costs + df[col].fillna(0)

        return revenue - costs
