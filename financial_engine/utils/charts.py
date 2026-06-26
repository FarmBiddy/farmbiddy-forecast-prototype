"""
Production chart generation using the Agg backend only.

Generates publication-quality PNG charts for reports and dashboards.
Never uses Tkinter or any GUI backend.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from financial_engine.forecasting.scenario_analysis import ScenarioComparison
from financial_engine.risk.financial_health import RiskScore
from financial_engine.shared.dairy_model import MonthlyForecastResult
from financial_engine.simulation.monte_carlo import SimulationResult
from financial_engine.simulation.sensitivity_analysis import SensitivityReport
from financial_engine.statistics.types import StatisticalForecastResult

# Publication-quality defaults
_STYLE = {
    "figure.figsize": (10, 5),
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
}
plt.rcParams.update(_STYLE)


class ChartBuilder:
    """Builds and saves matplotlib charts from engine outputs."""

    DPI = 150

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, figure: plt.Figure, filename: str) -> Path | None:
        if self.output_dir is None:
            return None
        path = self.output_dir / filename
        figure.savefig(path, dpi=self.DPI, bbox_inches="tight", facecolor="white")
        plt.close(figure)
        return path

    def plot_forecast_profit(self, forecast: MonthlyForecastResult) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(10, 5))
        forecast.monthly_profit.plot(ax=ax, color="#2E6F9E", marker="o", linewidth=2, label="Profit")
        ax.axhline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.set_title("12-Month Profit Forecast")
        ax.set_xlabel("Month")
        ax.set_ylabel("Profit (EUR)")
        ax.legend()
        fig.tight_layout()
        return fig

    def plot_cash_balance(self, forecast: MonthlyForecastResult) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(10, 5))
        forecast.cash_balance.plot(ax=ax, color="#2D8B57", marker="o", linewidth=2, label="Cash")
        threshold = forecast.assumptions.minimum_cash_threshold
        ax.axhline(threshold, color="#C0392B", linestyle="--", label=f"Min threshold (€{threshold:,.0f})")
        ax.axhline(0, color="grey", linestyle=":", linewidth=0.8)
        ax.set_title("Cash Balance Forecast")
        ax.set_xlabel("Month")
        ax.set_ylabel("Cash Balance (EUR)")
        ax.legend()
        fig.tight_layout()
        return fig

    def plot_confidence_bands(
        self, statistical: StatisticalForecastResult
    ) -> plt.Figure:
        """Plot statistical forecast with 95% prediction intervals."""
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.fill_between(
            statistical.periods,
            statistical.lower_prediction_95,
            statistical.upper_prediction_95,
            alpha=0.25,
            color="#2E6F9E",
            label="95% Prediction Interval",
        )
        statistical.forecast.plot(ax=ax, color="#2E6F9E", marker="o", linewidth=2, label="Forecast")
        ax.set_title(f"Forecast with Confidence Bands ({statistical.model_name})")
        ax.set_xlabel("Month")
        ax.set_ylabel("Value (EUR)")
        ax.legend()
        fig.tight_layout()
        return fig

    def plot_scenario_comparison(self, comparison: ScenarioComparison) -> plt.Figure:
        table = comparison.comparison_table
        metrics = ["total_profit", "total_revenue", "max_funding_requirement"]
        available = [m for m in metrics if m in table.columns]
        plot_data = table[available]

        fig, ax = plt.subplots(figsize=(10, 5))
        x = np.arange(len(plot_data.index))
        width = 0.25
        colors = ["#2E6F9E", "#E07B39", "#7B68AE"]

        for i, col in enumerate(available):
            ax.bar(
                x + i * width, plot_data[col], width,
                label=col.replace("_", " ").title(), color=colors[i % 3],
            )

        ax.set_xticks(x + width)
        ax.set_xticklabels(plot_data.index.str.title())
        ax.set_title("Scenario Comparison")
        ax.set_ylabel("EUR")
        ax.legend()
        fig.tight_layout()
        return fig

    def plot_monte_carlo_distribution(self, simulation: SimulationResult) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(
            simulation.annual_profits, bins=50,
            color="#2E6F9E", edgecolor="white", alpha=0.85,
        )
        ax.axvline(simulation.expected_profit, color="#C0392B", linestyle="--",
                   label=f"Mean €{simulation.expected_profit:,.0f}")
        ax.axvline(simulation.median_profit, color="#E07B39", linestyle="--",
                   label=f"Median €{simulation.median_profit:,.0f}")
        ax.axvline(simulation.percentile_5, color="grey", linestyle=":",
                   label=f"P5 €{simulation.percentile_5:,.0f}")
        ax.axvline(simulation.percentile_95, color="grey", linestyle=":",
                   label=f"P95 €{simulation.percentile_95:,.0f}")
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title(f"Monte Carlo Distribution ({simulation.iterations:,} simulations)")
        ax.set_xlabel("Annual Profit (EUR)")
        ax.set_ylabel("Frequency")
        ax.legend(fontsize=9)
        fig.tight_layout()
        return fig

    def plot_sensitivity_tornado(self, sensitivity: SensitivityReport) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(10, 6))
        names = [r.display_name for r in reversed(sensitivity.results)]
        lows = [r.profit_at_low for r in reversed(sensitivity.results)]
        highs = [r.profit_at_high for r in reversed(sensitivity.results)]
        base = sensitivity.base_annual_profit

        y_pos = np.arange(len(names))
        left = [l - base for l in lows]
        right = [h - base for h in highs]

        ax.barh(y_pos, left, color="#E07B39", alpha=0.8, label="Low (−10%)")
        ax.barh(y_pos, right, color="#2E6F9E", alpha=0.8, label="High (+10%)")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title("Sensitivity Analysis — Profit Impact")
        ax.set_xlabel("Deviation from Base Profit (EUR)")
        ax.legend()
        fig.tight_layout()
        return fig

    def plot_risk_breakdown(self, risk: RiskScore) -> plt.Figure:
        """Horizontal bar chart of risk dimension scores."""
        fig, ax = plt.subplots(figsize=(10, 5))
        if risk.assessment:
            dims = risk.assessment.dimensions
            names = [d.display_name for d in dims]
            scores = [d.score for d in dims]
            colors = ["#2D8B57" if s < 40 else "#E07B39" if s < 65 else "#C0392B" for s in scores]
            y_pos = np.arange(len(names))
            ax.barh(y_pos, scores, color=colors, alpha=0.85)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(names)
            ax.set_xlim(0, 100)
            ax.set_title(f"Risk Breakdown (Health: {risk.health_score:.0f}/100)")
            ax.set_xlabel("Risk Score (0–100)")
        else:
            components = risk.components
            names = list(components.keys())[:5]
            scores = [components[n] for n in names]
            ax.barh(names, scores, color="#2E6F9E", alpha=0.85)
            ax.set_title("Risk Component Scores")
            ax.set_xlabel("Score")
        fig.tight_layout()
        return fig

    def generate_all(
        self,
        forecast: MonthlyForecastResult,
        scenarios: ScenarioComparison,
        simulation: SimulationResult,
        sensitivity: SensitivityReport,
        risk: RiskScore | None = None,
        statistical_forecast: StatisticalForecastResult | None = None,
    ) -> dict[str, str]:
        """Generate and save all standard charts."""
        charts: dict[str, str] = {}
        specs: list[tuple[str, plt.Figure]] = [
            ("forecast_profit", self.plot_forecast_profit(forecast)),
            ("cash_balance", self.plot_cash_balance(forecast)),
            ("scenario_comparison", self.plot_scenario_comparison(scenarios)),
            ("monte_carlo_distribution", self.plot_monte_carlo_distribution(simulation)),
            ("sensitivity_tornado", self.plot_sensitivity_tornado(sensitivity)),
        ]
        if risk is not None:
            specs.append(("risk_breakdown", self.plot_risk_breakdown(risk)))
        if statistical_forecast is not None:
            specs.append(("confidence_bands", self.plot_confidence_bands(statistical_forecast)))

        for name, fig in specs:
            path = self.save(fig, f"{name}.png")
            if path:
                charts[name] = str(path)
        return charts
