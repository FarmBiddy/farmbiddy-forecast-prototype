"""
Core dairy farm financial model — shared calculation engine.

All forecasting, simulation, and risk modules delegate to this module so that
future statistical (Phase 2) and ML (Phase 3) models can plug in via the
same ``DairyFinancialModel`` interface without changing downstream consumers.

Monthly P&L logic (deterministic):
    Milk Revenue     = herd × yield × price × seasonality
    Feed Costs       = herd × feed_cost_per_cow × inflation
    Labour / Vet / Operating = base monthly × inflation
    Interest         = total_debt × annual_rate / 12
    Debt Repayments  = fixed monthly
    Monthly Profit   = revenue − all costs
    Cash Balance     = opening + cumulative profit
    Funding Req.     = shortfall below minimum cash threshold
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field


class DairyFarmAssumptions(BaseModel):
    """
    Configurable assumptions for a dairy farm financial forecast.

    All monetary values are in EUR unless noted. Rates are expressed as
    decimals (e.g. 0.05 = 5 %).
    """

    herd_size: int = Field(default=120, gt=0, description="Number of milking cows")
    milk_yield_per_cow: float = Field(
        default=550.0, gt=0, description="Litres per cow per month"
    )
    milk_price: float = Field(default=0.42, gt=0, description="EUR per litre")
    feed_cost_per_cow: float = Field(
        default=95.0, gt=0, description="EUR feed cost per cow per month"
    )
    labour_cost_monthly: float = Field(default=12_000.0, ge=0)
    veterinary_cost_monthly: float = Field(default=1_500.0, ge=0)
    operating_cost_monthly: float = Field(default=4_500.0, ge=0)
    debt_repayment_monthly: float = Field(default=3_500.0, ge=0)
    total_debt: float = Field(default=250_000.0, ge=0)
    interest_rate_annual: float = Field(default=0.055, ge=0, description="Annual interest rate")
    inflation_rate_annual: float = Field(default=0.03, ge=0, description="Annual inflation rate")
    opening_cash_balance: float = Field(default=50_000.0)
    minimum_cash_threshold: float = Field(
        default=15_000.0,
        description="Cash level below which external funding is required",
    )
    horizon_months: int = Field(default=12, gt=0, le=120)
    scenario_name: str = Field(default="base")

    def annual_revenue_estimate(self) -> float:
        """Rough annual milk revenue used for ratio calculations."""
        return self.herd_size * self.milk_yield_per_cow * self.milk_price * 12


class ScenarioModifiers(BaseModel):
    """
    Multiplicative and additive adjustments applied on top of base assumptions.

    Used by scenario analysis, sensitivity analysis, and Monte Carlo sampling.
    """

    milk_price_multiplier: float = Field(default=1.0, gt=0)
    milk_yield_multiplier: float = Field(default=1.0, gt=0)
    feed_cost_multiplier: float = Field(default=1.0, gt=0)
    operating_cost_multiplier: float = Field(default=1.0, gt=0)
    labour_cost_multiplier: float = Field(default=1.0, gt=0)
    inflation_rate_adjustment: float = Field(
        default=0.0, description="Added to annual inflation rate"
    )
    interest_rate_adjustment: float = Field(
        default=0.0, description="Added to annual interest rate"
    )
    unexpected_expense: float = Field(
        default=0.0, ge=0, description="One-off cost applied in a random month (MC)"
    )
    unexpected_expense_month: int | None = Field(
        default=None, description="Month index (0-based) for unexpected expense"
    )


# Pre-built scenario presets for advisor-facing analysis
SCENARIO_PRESETS: dict[str, ScenarioModifiers] = {
    "base": ScenarioModifiers(),
    "optimistic": ScenarioModifiers(
        milk_price_multiplier=1.08,
        milk_yield_multiplier=1.05,
        feed_cost_multiplier=0.95,
        operating_cost_multiplier=0.97,
        labour_cost_multiplier=0.98,
        inflation_rate_adjustment=-0.01,
        interest_rate_adjustment=-0.005,
    ),
    "pessimistic": ScenarioModifiers(
        milk_price_multiplier=0.90,
        milk_yield_multiplier=0.95,
        feed_cost_multiplier=1.10,
        operating_cost_multiplier=1.05,
        labour_cost_multiplier=1.03,
        inflation_rate_adjustment=0.02,
        interest_rate_adjustment=0.01,
    ),
}


@dataclass
class MonthlyForecastResult:
    """Complete monthly forecast output for a dairy farm."""

    periods: pd.DatetimeIndex
    milk_revenue: pd.Series
    feed_costs: pd.Series
    labour_costs: pd.Series
    veterinary_costs: pd.Series
    operating_costs: pd.Series
    interest_costs: pd.Series
    debt_repayments: pd.Series
    monthly_profit: pd.Series
    cash_balance: pd.Series
    funding_requirement: pd.Series
    assumptions: DairyFarmAssumptions
    modifiers: ScenarioModifiers
    model_name: str = "deterministic"
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def total_profit(self) -> float:
        return float(self.monthly_profit.sum())

    @property
    def total_revenue(self) -> float:
        return float(self.milk_revenue.sum())

    @property
    def profit_margin(self) -> float:
        rev = self.total_revenue
        return self.total_profit / rev if rev else 0.0

    @property
    def max_funding_requirement(self) -> float:
        return float(self.funding_requirement.max())

    @property
    def min_cash_balance(self) -> float:
        return float(self.cash_balance.min())

    def to_dataframe(self) -> pd.DataFrame:
        """Return all line items as a single DataFrame."""
        return pd.DataFrame(
            {
                "milk_revenue": self.milk_revenue,
                "feed_costs": self.feed_costs,
                "labour_costs": self.labour_costs,
                "veterinary_costs": self.veterinary_costs,
                "operating_costs": self.operating_costs,
                "interest_costs": self.interest_costs,
                "debt_repayments": self.debt_repayments,
                "monthly_profit": self.monthly_profit,
                "cash_balance": self.cash_balance,
                "funding_requirement": self.funding_requirement,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise forecast for JSON export."""
        df = self.to_dataframe()
        return {
            "model_name": self.model_name,
            "scenario_name": self.assumptions.scenario_name,
            "summary": {
                "total_profit": round(self.total_profit, 2),
                "total_revenue": round(self.total_revenue, 2),
                "profit_margin": round(self.profit_margin, 4),
                "max_funding_requirement": round(self.max_funding_requirement, 2),
                "min_cash_balance": round(self.min_cash_balance, 2),
            },
            "monthly": {
                col: {str(idx.date()): round(val, 2) for idx, val in df[col].items()}
                for col in df.columns
            },
            "metadata": self.metadata,
        }


@dataclass
class AnnualSummary:
    """Aggregated annual metrics — used by Monte Carlo and risk modules."""

    annual_profit: float
    min_cash_balance: float
    max_funding_requirement: float
    had_negative_cash: bool
    had_funding_requirement: bool
    profit_margin: float
    debt_ratio: float
    monthly_profit_std: float


class DairyFinancialModel:
    """
    Shared financial calculation engine for dairy farm forecasting.

    Phase 2 statistical models and Phase 3 ML models will implement the
    same output types (``MonthlyForecastResult``, ``AnnualSummary``) so the
    pipeline, risk, and advisor layers remain unchanged.
    """

    @staticmethod
    def _seasonality_factor(month_index: int) -> float:
        """Mild seasonal swing in milk production (peak spring/autumn)."""
        return 1.0 + 0.04 * math.sin(2 * math.pi * (month_index - 2) / 12)

    @classmethod
    def apply_modifiers(
        cls,
        base: DairyFarmAssumptions,
        modifiers: ScenarioModifiers | None = None,
    ) -> DairyFarmAssumptions:
        """Return a new assumptions object with scenario modifiers applied."""
        m = modifiers or ScenarioModifiers()
        return base.model_copy(
            update={
                "milk_price": base.milk_price * m.milk_price_multiplier,
                "milk_yield_per_cow": base.milk_yield_per_cow * m.milk_yield_multiplier,
                "feed_cost_per_cow": base.feed_cost_per_cow * m.feed_cost_multiplier,
                "operating_cost_monthly": base.operating_cost_monthly * m.operating_cost_multiplier,
                "labour_cost_monthly": base.labour_cost_monthly * m.labour_cost_multiplier,
                "inflation_rate_annual": max(0.0, base.inflation_rate_annual + m.inflation_rate_adjustment),
                "interest_rate_annual": max(0.0, base.interest_rate_annual + m.interest_rate_adjustment),
            }
        )

    @classmethod
    def compute_forecast(
        cls,
        assumptions: DairyFarmAssumptions,
        modifiers: ScenarioModifiers | None = None,
        start_date: pd.Timestamp | None = None,
    ) -> MonthlyForecastResult:
        """
        Build a full monthly forecast for the configured horizon.

        This is the primary entry point used by deterministic forecasting,
        scenario analysis, and sensitivity analysis.
        """
        m = modifiers or ScenarioModifiers()
        effective = cls.apply_modifiers(assumptions, m)
        horizon = effective.horizon_months
        periods = pd.date_range(
            start=start_date or pd.Timestamp.today().normalize().replace(day=1),
            periods=horizon,
            freq="ME",
        )

        milk_revenue: list[float] = []
        feed_costs: list[float] = []
        labour_costs: list[float] = []
        veterinary_costs: list[float] = []
        operating_costs: list[float] = []
        interest_costs: list[float] = []
        debt_repayments: list[float] = []
        monthly_profit: list[float] = []
        cash_balance: list[float] = []
        funding_requirement: list[float] = []

        cash = effective.opening_cash_balance
        monthly_interest = effective.total_debt * effective.interest_rate_annual / 12

        for month_idx in range(horizon):
            inflation = (1 + effective.inflation_rate_annual) ** (month_idx / 12)
            season = cls._seasonality_factor(month_idx)

            litres = effective.herd_size * effective.milk_yield_per_cow * season
            revenue = litres * effective.milk_price
            feed = effective.herd_size * effective.feed_cost_per_cow * inflation
            labour = effective.labour_cost_monthly * inflation
            vet = effective.veterinary_cost_monthly * inflation
            operating = effective.operating_cost_monthly * inflation
            interest = monthly_interest
            debt = effective.debt_repayment_monthly

            # One-off unexpected expense (Monte Carlo)
            unexpected = 0.0
            if m.unexpected_expense > 0:
                target_month = m.unexpected_expense_month if m.unexpected_expense_month is not None else 5
                if month_idx == target_month:
                    unexpected = m.unexpected_expense
                    operating += unexpected

            profit = revenue - feed - labour - vet - operating - interest - debt
            cash += profit
            funding = max(0.0, effective.minimum_cash_threshold - cash)

            milk_revenue.append(revenue)
            feed_costs.append(feed)
            labour_costs.append(labour)
            veterinary_costs.append(vet)
            operating_costs.append(operating)
            interest_costs.append(interest)
            debt_repayments.append(debt)
            monthly_profit.append(profit)
            cash_balance.append(cash)
            funding_requirement.append(funding)

        return MonthlyForecastResult(
            periods=periods,
            milk_revenue=pd.Series(milk_revenue, index=periods, name="milk_revenue"),
            feed_costs=pd.Series(feed_costs, index=periods, name="feed_costs"),
            labour_costs=pd.Series(labour_costs, index=periods, name="labour_costs"),
            veterinary_costs=pd.Series(veterinary_costs, index=periods, name="veterinary_costs"),
            operating_costs=pd.Series(operating_costs, index=periods, name="operating_costs"),
            interest_costs=pd.Series(interest_costs, index=periods, name="interest_costs"),
            debt_repayments=pd.Series(debt_repayments, index=periods, name="debt_repayments"),
            monthly_profit=pd.Series(monthly_profit, index=periods, name="monthly_profit"),
            cash_balance=pd.Series(cash_balance, index=periods, name="cash_balance"),
            funding_requirement=pd.Series(funding_requirement, index=periods, name="funding_requirement"),
            assumptions=effective,
            modifiers=m,
            model_name="deterministic",
            metadata={"unexpected_expense": str(m.unexpected_expense)},
        )

    @classmethod
    def compute_annual_summary(
        cls,
        assumptions: DairyFarmAssumptions,
        modifiers: ScenarioModifiers | None = None,
    ) -> AnnualSummary:
        """Compute aggregated annual metrics — primary output for Monte Carlo."""
        forecast = cls.compute_forecast(assumptions, modifiers)
        revenue = forecast.total_revenue
        debt_ratio = assumptions.total_debt / revenue if revenue else 0.0
        return AnnualSummary(
            annual_profit=forecast.total_profit,
            min_cash_balance=forecast.min_cash_balance,
            max_funding_requirement=forecast.max_funding_requirement,
            had_negative_cash=forecast.min_cash_balance < 0,
            had_funding_requirement=forecast.max_funding_requirement > 0,
            profit_margin=forecast.profit_margin,
            debt_ratio=debt_ratio,
            monthly_profit_std=float(forecast.monthly_profit.std()),
        )
