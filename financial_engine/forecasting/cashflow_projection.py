"""
Cashflow projection for dairy farm operations.

Wraps ``MonthlyForecastResult`` into a cashflow view.  Future statistical
models will feed their forecasts through the same projection layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from financial_engine.shared.dairy_model import (
    DairyFarmAssumptions,
    DairyFinancialModel,
    MonthlyForecastResult,
    ScenarioModifiers,
)


@dataclass
class CashflowProjection:
    """Structured cashflow forecast output."""

    periods: pd.DatetimeIndex
    inflows: pd.Series
    outflows: pd.Series
    net_cashflow: pd.Series
    cumulative_balance: pd.Series
    funding_requirement: pd.Series


class CashflowProjector:
    """
    Projects farm cash inflows and outflows from a monthly forecast.

    Inflows  = milk revenue
    Outflows = all cost categories + debt service
    """

    def __init__(
        self,
        assumptions: DairyFarmAssumptions | None = None,
        modifiers: ScenarioModifiers | None = None,
    ) -> None:
        self.assumptions = assumptions or DairyFarmAssumptions()
        self.modifiers = modifiers or ScenarioModifiers()
        self._forecast: MonthlyForecastResult | None = None

    def set_opening_balance(self, balance: float) -> None:
        """Override opening cash balance on assumptions."""
        self.assumptions = self.assumptions.model_copy(
            update={"opening_cash_balance": balance}
        )

    def project(self, horizon: int | None = None) -> CashflowProjection:
        """Build cashflow from the underlying financial model."""
        if horizon is not None:
            self.assumptions = self.assumptions.model_copy(
                update={"horizon_months": horizon}
            )
        self._forecast = DairyFinancialModel.compute_forecast(
            self.assumptions, self.modifiers
        )
        f = self._forecast
        outflows = (
            f.feed_costs
            + f.labour_costs
            + f.veterinary_costs
            + f.operating_costs
            + f.interest_costs
            + f.debt_repayments
        )
        return CashflowProjection(
            periods=f.periods,
            inflows=f.milk_revenue,
            outflows=outflows,
            net_cashflow=f.monthly_profit,
            cumulative_balance=f.cash_balance,
            funding_requirement=f.funding_requirement,
        )

    @property
    def last_forecast(self) -> MonthlyForecastResult | None:
        return self._forecast
