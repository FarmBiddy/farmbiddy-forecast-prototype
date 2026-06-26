"""
Composite financial risk scoring — backwards-compatible re-export.

The production implementation lives in ``financial_health.py``.
This module preserves the original import paths used by the pipeline and tests.
"""

from financial_engine.risk.financial_health import (
    FinancialHealthAssessment,
    FinancialHealthEngine,
    RiskDimension,
    RiskScore,
    RiskScorer,
    RiskTier,
)

__all__ = [
    "FinancialHealthAssessment",
    "FinancialHealthEngine",
    "RiskDimension",
    "RiskScore",
    "RiskScorer",
    "RiskTier",
]
