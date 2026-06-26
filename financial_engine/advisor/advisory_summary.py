"""
Advisory summary generation for farm financial intelligence.

This module will eventually contain:
- Executive summary of forecast, risk, and recommendation outputs
- Structured narrative templates for advisor-facing reports
- Key metric highlights and trend commentary
- Multi-scenario summary comparisons
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from financial_engine.advisor.recommendations import Recommendation


@dataclass
class AdvisorySummary:
    """Complete advisory summary for a farm analysis run."""

    generated_at: datetime
    headline: str
    key_findings: list[str] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


class AdvisorySummaryGenerator:
    """
    Synthesises engine outputs into a coherent advisory summary.

    Future responsibilities:
    - Combine forecasts, risk scores, and recommendations
    - Generate natural-language narratives (template-based initially)
    - Support export to JSON for downstream consumption by FarmBiddy
    """

    def generate(
        self,
        headline: str,
        key_findings: list[str] | None = None,
        recommendations: list[Recommendation] | None = None,
    ) -> AdvisorySummary:
        """Build an advisory summary from provided components."""
        return AdvisorySummary(
            generated_at=datetime.now(),
            headline=headline,
            key_findings=key_findings or [],
            recommendations=recommendations or [],
            metadata={"version": "0.1.0", "status": "placeholder"},
        )

    def to_dict(self, summary: AdvisorySummary) -> dict[str, object]:
        """Serialize an advisory summary to a dictionary."""
        return {
            "generated_at": summary.generated_at.isoformat(),
            "headline": summary.headline,
            "key_findings": summary.key_findings,
            "recommendations": [
                {
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority.value,
                    "category": r.category,
                }
                for r in summary.recommendations
            ],
            "metadata": summary.metadata,
        }
