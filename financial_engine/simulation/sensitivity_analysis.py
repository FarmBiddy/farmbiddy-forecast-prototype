"""
Sensitivity analysis — ranked impact of key variables on annual profit.

Uses one-at-a-time (OAT) perturbation via the shared ``DairyFinancialModel``.
Variables analysed: Milk Price, Feed Costs, Milk Yield, Labour Costs,
Interest Rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from financial_engine.shared.dairy_model import (
    DairyFarmAssumptions,
    DairyFinancialModel,
    ScenarioModifiers,
)


@dataclass
class SensitivityResult:
    """Result of sensitivity analysis on a single parameter."""

    parameter: str
    display_name: str
    base_value: float
    low_value: float
    high_value: float
    profit_at_low: float
    profit_at_high: float
    profit_at_base: float
    impact_range: float
    elasticity: float
    rank: int = 0
    # Multi-metric impacts (Phase 2 production extension)
    cashflow_at_low: float = 0.0
    cashflow_at_high: float = 0.0
    funding_at_low: float = 0.0
    funding_at_high: float = 0.0
    risk_impact: float = 0.0


@dataclass
class SensitivityMultiReport:
    """Sensitivity ranked across profit, cashflow, funding, and risk."""

    profit_ranking: list[SensitivityResult]
    cashflow_ranking: list[SensitivityResult]
    funding_ranking: list[SensitivityResult]
    risk_ranking: list[SensitivityResult]
    base_annual_profit: float

    def to_dict(self) -> dict[str, Any]:
        def _ranked(results: list[SensitivityResult]) -> list[dict[str, Any]]:
            return [
                {
                    "rank": r.rank,
                    "parameter": r.parameter,
                    "display_name": r.display_name,
                    "impact_range": round(r.impact_range, 2),
                    "risk_impact": round(r.risk_impact, 2),
                }
                for r in results
            ]

        return {
            "base_annual_profit": round(self.base_annual_profit, 2),
            "profit_ranking": _ranked(self.profit_ranking),
            "cashflow_ranking": _ranked(self.cashflow_ranking),
            "funding_ranking": _ranked(self.funding_ranking),
            "risk_ranking": _ranked(self.risk_ranking),
        }


@dataclass
class SensitivityReport:
    """Full ranked sensitivity output."""

    results: list[SensitivityResult]
    base_annual_profit: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_annual_profit": round(self.base_annual_profit, 2),
            "ranked_results": [
                {
                    "rank": r.rank,
                    "parameter": r.parameter,
                    "display_name": r.display_name,
                    "base_value": round(r.base_value, 4),
                    "low_value": round(r.low_value, 4),
                    "high_value": round(r.high_value, 4),
                    "profit_at_low": round(r.profit_at_low, 2),
                    "profit_at_high": round(r.profit_at_high, 2),
                    "impact_range": round(r.impact_range, 2),
                    "elasticity": round(r.elasticity, 4),
                }
                for r in self.results
            ],
        }


# Maps parameter keys to modifier fields and display labels
SENSITIVITY_PARAMETERS: dict[str, dict[str, str]] = {
    "milk_price": {"field": "milk_price_multiplier", "display": "Milk Price"},
    "feed_costs": {"field": "feed_cost_multiplier", "display": "Feed Costs"},
    "milk_yield": {"field": "milk_yield_multiplier", "display": "Milk Yield"},
    "labour_costs": {"field": "labour_cost_multiplier", "display": "Labour Costs"},
    "interest_rate": {"field": "interest_rate_adjustment", "display": "Interest Rate"},
}


class SensitivityAnalyser:
    """
    One-at-a-time sensitivity on profit, ranked by absolute impact range.

    Future: global sensitivity (Sobol) and multi-parameter interactions.
    """

    def __init__(
        self,
        assumptions: DairyFarmAssumptions | None = None,
        perturbation_pct: float = 0.10,
    ) -> None:
        self.assumptions = assumptions or DairyFarmAssumptions()
        self.perturbation_pct = perturbation_pct

    def _annual_summary(self, modifiers: ScenarioModifiers):
        return DairyFinancialModel.compute_annual_summary(self.assumptions, modifiers)

    def _profit_with_modifier(self, modifiers: ScenarioModifiers) -> float:
        return self._annual_summary(modifiers).annual_profit

    def _base_value(self, param: str) -> float:
        a = self.assumptions
        mapping = {
            "milk_price": a.milk_price,
            "feed_costs": a.feed_cost_per_cow,
            "milk_yield": a.milk_yield_per_cow,
            "labour_costs": a.labour_cost_monthly,
            "interest_rate": a.interest_rate_annual,
        }
        return mapping[param]

    def _build_modifier(self, param: str, direction: str) -> ScenarioModifiers:
        """Build modifiers for low (-pct) or high (+pct) perturbation."""
        pct = self.perturbation_pct
        m = ScenarioModifiers()

        if param == "milk_price":
            factor = 1 - pct if direction == "low" else 1 + pct
            return m.model_copy(update={"milk_price_multiplier": factor})
        if param == "feed_costs":
            factor = 1 - pct if direction == "low" else 1 + pct
            return m.model_copy(update={"feed_cost_multiplier": factor})
        if param == "milk_yield":
            factor = 1 - pct if direction == "low" else 1 + pct
            return m.model_copy(update={"milk_yield_multiplier": factor})
        if param == "labour_costs":
            factor = 1 - pct if direction == "low" else 1 + pct
            return m.model_copy(update={"labour_cost_multiplier": factor})
        if param == "interest_rate":
            delta = -pct * self.assumptions.interest_rate_annual if direction == "low" else pct * self.assumptions.interest_rate_annual
            return m.model_copy(update={"interest_rate_adjustment": delta})
        return m

    def analyse_parameter(self, param: str) -> SensitivityResult:
        """Run OAT sensitivity on a single parameter across all metrics."""
        meta = SENSITIVITY_PARAMETERS[param]
        base_val = self._base_value(param)
        base_mod = ScenarioModifiers()
        base_summary = self._annual_summary(base_mod)
        low_mod = self._build_modifier(param, "low")
        high_mod = self._build_modifier(param, "high")
        low_summary = self._annual_summary(low_mod)
        high_summary = self._annual_summary(high_mod)

        base_profit = base_summary.annual_profit
        profit_low = low_summary.annual_profit
        profit_high = high_summary.annual_profit
        impact = abs(profit_high - profit_low)
        elasticity = (
            ((profit_high - profit_low) / base_profit) / (2 * self.perturbation_pct)
            if base_profit
            else 0.0
        )
        delta = base_val * self.perturbation_pct
        risk_impact = abs(low_summary.profit_margin - high_summary.profit_margin)

        return SensitivityResult(
            parameter=param,
            display_name=meta["display"],
            base_value=base_val,
            low_value=base_val - delta,
            high_value=base_val + delta,
            profit_at_low=profit_low,
            profit_at_high=profit_high,
            profit_at_base=base_profit,
            impact_range=impact,
            elasticity=elasticity,
            cashflow_at_low=low_summary.min_cash_balance,
            cashflow_at_high=high_summary.min_cash_balance,
            funding_at_low=low_summary.max_funding_requirement,
            funding_at_high=high_summary.max_funding_requirement,
            risk_impact=risk_impact,
        )

    def analyse_all(self) -> SensitivityReport:
        """Analyse all configured parameters and rank by profit impact."""
        base_profit = self._profit_with_modifier(ScenarioModifiers())
        results = [self.analyse_parameter(p) for p in SENSITIVITY_PARAMETERS]
        results.sort(key=lambda r: r.impact_range, reverse=True)
        for rank, result in enumerate(results, start=1):
            result.rank = rank
        return SensitivityReport(results=results, base_annual_profit=base_profit)

    def analyse_comprehensive(self) -> SensitivityMultiReport:
        """Rank variables by impact on profit, cashflow, funding, and risk."""
        base_profit = self._profit_with_modifier(ScenarioModifiers())
        results = [self.analyse_parameter(p) for p in SENSITIVITY_PARAMETERS]

        profit_ranking = sorted(results, key=lambda r: r.impact_range, reverse=True)
        cashflow_ranking = sorted(
            results,
            key=lambda r: abs(r.cashflow_at_high - r.cashflow_at_low),
            reverse=True,
        )
        funding_ranking = sorted(
            results,
            key=lambda r: abs(r.funding_at_high - r.funding_at_low),
            reverse=True,
        )
        risk_ranking = sorted(results, key=lambda r: r.risk_impact, reverse=True)

        for lst in (profit_ranking, cashflow_ranking, funding_ranking, risk_ranking):
            for rank, item in enumerate(lst, start=1):
                item.rank = rank

        return SensitivityMultiReport(
            profit_ranking=profit_ranking,
            cashflow_ranking=cashflow_ranking,
            funding_ranking=funding_ranking,
            risk_ranking=risk_ranking,
            base_annual_profit=base_profit,
        )

    def to_tornado_data(self, report: SensitivityReport) -> pd.DataFrame:
        """Format sensitivity results for tornado chart visualisation."""
        return pd.DataFrame(
            [
                {
                    "parameter": r.display_name,
                    "profit_at_low": r.profit_at_low,
                    "profit_at_high": r.profit_at_high,
                    "profit_at_base": r.profit_at_base,
                    "impact_range": r.impact_range,
                    "rank": r.rank,
                }
                for r in report.results
            ]
        )
