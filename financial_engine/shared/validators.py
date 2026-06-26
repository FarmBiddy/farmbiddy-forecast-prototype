"""
Input validation for financial data and model parameters.

This module will eventually contain:
- Schema validation for incoming farm financial records
- Range and consistency checks on assumptions
- Time-series completeness and gap detection
- Cross-field business rule validation
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field, field_validator


class ValidationResult(BaseModel):
    """Outcome of a validation pass."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DataValidator:
    """
    Validates DataFrames and configuration objects before model execution.

    Future responsibilities:
    - Pluggable validation rules per data source
    - Detailed error reporting for integration with upstream systems
    """

    @staticmethod
    def validate_time_series(df: pd.DataFrame, date_column: str) -> ValidationResult:
        """
        Perform basic time-series structure checks.

        Args:
            df: Input DataFrame to validate.
            date_column: Name of the column containing dates.

        Returns:
            ValidationResult indicating pass/fail with explanatory messages.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if date_column not in df.columns:
            errors.append(f"Missing required date column: {date_column}")
            return ValidationResult(is_valid=False, errors=errors)

        if df[date_column].isna().any():
            warnings.append(f"Null values found in {date_column}")

        if not pd.api.types.is_datetime64_any_dtype(df[date_column]):
            try:
                pd.to_datetime(df[date_column])
            except (ValueError, TypeError) as exc:
                errors.append(f"Column {date_column} is not parseable as datetime: {exc}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def validate_numeric_columns(
        df: pd.DataFrame,
        columns: list[str],
    ) -> ValidationResult:
        """Ensure specified columns exist and contain numeric data."""
        errors: list[str] = []
        for col in columns:
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")
            elif not pd.api.types.is_numeric_dtype(df[col]):
                errors.append(f"Column {col} must be numeric")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


class ForecastConfigValidator(BaseModel):
    """Placeholder validator for forecast configuration objects."""

    horizon: int = Field(..., gt=0, description="Number of periods to forecast")
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    @field_validator("horizon")
    @classmethod
    def horizon_reasonable(cls, value: int) -> int:
        """Warn-level checks will be expanded; hard limit prevents runaway jobs."""
        if value > 120:
            raise ValueError("Forecast horizon exceeds maximum supported value (120)")
        return value
