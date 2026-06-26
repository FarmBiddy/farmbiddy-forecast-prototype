"""Decision-support advisory and explainability layer."""

from financial_engine.advisor.advisory_summary import AdvisorySummaryGenerator
from financial_engine.advisor.explainability import (
    ExplainabilityEngine,
    ExplainabilityReport,
    Explanation,
    ModelExplainer,
)
from financial_engine.advisor.recommendations import (
    AdvisoryNarrative,
    Recommendation,
    RecommendationEngine,
    RecommendationPriority,
)

__all__ = [
    "AdvisoryNarrative",
    "AdvisorySummaryGenerator",
    "ExplainabilityEngine",
    "ExplainabilityReport",
    "Explanation",
    "ModelExplainer",
    "Recommendation",
    "RecommendationEngine",
    "RecommendationPriority",
]
