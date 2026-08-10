"""Shared number-formatting helpers for backend-generated display strings.

Mirrors the frontend helpers in ``frontend/app.js`` (Phase 9 / UX items 11-12):
negative currency values are always shown as "-€1,234" (sign before the
symbol), never "€-1,234", and percentages default to one decimal place.
This module has no project dependencies so it can be imported anywhere
without risking circular imports.
"""

from __future__ import annotations


def format_currency(value: float | int | None, decimals: int = 0) -> str:
    """Format a number as euro currency, e.g. -1234.5 -> "-€1,235"."""
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        num = 0.0
    sign = "-" if num < 0 else ""
    return f"{sign}€{abs(num):,.{decimals}f}"


def format_percent(value: float | int | None, decimals: int = 1) -> str:
    """Format a number as a percentage string, e.g. 12.34 -> "12.3%"."""
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        num = 0.0
    return f"{num:.{decimals}f}%"
