"""
Funding and liquidity risk assessment for farm operations.

This module will eventually contain:
- Debt service coverage ratio projections
- Working capital adequacy under stress scenarios
- Loan covenant breach probability
- Funding gap identification and timing analysis
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from financial_engine.forecasting.cashflow_projection import CashflowProjection


@dataclass
class FundingRiskAssessment:
    """Structured funding risk output."""

    liquidity_runway_months: int
    minimum_cash_balance: float
    covenant_breach_probability: float
    risk_level: str


class FundingRiskAssessor:
    """
    Evaluates whether a farm can meet its funding obligations.

    Future responsibilities:
    - Analyse cashflow projections for liquidity shortfalls
    - Model debt repayment schedules against projected income
    - Flag high-risk periods and recommend mitigation actions
    """

    def __init__(self, minimum_balance_threshold: float = 0.0) -> None:
        self.minimum_balance_threshold = minimum_balance_threshold

    def assess(self, cashflow: CashflowProjection) -> FundingRiskAssessment:
        """
        Perform placeholder funding risk assessment.

        Full covenant and runway logic will be added in a future iteration.
        """
        min_balance = float(cashflow.cumulative_balance.min())
        below_threshold = cashflow.cumulative_balance < self.minimum_balance_threshold
        runway = int((~below_threshold).sum()) if not below_threshold.all() else 0
        return FundingRiskAssessment(
            liquidity_runway_months=runway,
            minimum_cash_balance=min_balance,
            covenant_breach_probability=0.0,
            risk_level="unknown",
        )

    def stress_test(
        self,
        cashflow: CashflowProjection,
        shock_pct: float,
    ) -> pd.DataFrame:
        """Apply a revenue shock and return adjusted cashflow (placeholder)."""
        shocked_outflows = cashflow.outflows * (1 + shock_pct)
        return pd.DataFrame(
            {
                "period": cashflow.periods,
                "outflows": shocked_outflows,
                "cumulative_balance": cashflow.cumulative_balance,
            }
        )
