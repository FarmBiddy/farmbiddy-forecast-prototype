"""
Economic and operational assumptions for forecasting and simulation.

This module will eventually contain:
- Pydantic models for farm-specific assumptions (yields, prices, costs)
- Inflation and interest-rate assumptions
- Seasonal adjustment parameters
- Assumption versioning and scenario overrides
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class EconomicAssumption(BaseModel):
    """A single named economic assumption with metadata."""

    name: str = Field(..., description="Human-readable assumption identifier")
    value: float = Field(..., description="Numeric assumption value")
    unit: str = Field(default="", description="Unit of measure (e.g. EUR/ha, %)")
    effective_date: date | None = Field(
        default=None,
        description="Date from which this assumption applies",
    )
    notes: str = Field(default="", description="Optional context or source reference")


class AssumptionSet(BaseModel):
    """
    Collection of assumptions used across forecasting and simulation pipelines.

    Future responsibilities:
    - Load assumptions from structured files or databases
    - Merge base assumptions with scenario-specific overrides
    - Validate internal consistency (e.g. price vs. cost relationships)
    """

    assumptions: list[EconomicAssumption] = Field(default_factory=list)
    scenario_name: str = Field(default="base", description="Scenario identifier")

    def get(self, name: str) -> EconomicAssumption | None:
        """Return the first assumption matching the given name."""
        for assumption in self.assumptions:
            if assumption.name == name:
                return assumption
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize assumptions to a plain dictionary for downstream use."""
        return self.model_dump()
