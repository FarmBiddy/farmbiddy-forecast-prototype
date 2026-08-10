"""
Classify cash-flow shortages as short-term/once-off vs long-term/structural
(Teagasc item 3).

Runs against the chronological budget-vs-actual entries produced by
services/cashflow_budget_service.py. A deficit month is:

- **long-term/structural** if it's part of a persistent run of consecutive
  deficit months, or the farm's debt is high relative to revenue, or its
  profit margin is persistently low - i.e. detectable from a multi-month
  pattern or a debt/margin ratio breach (Phase 1's debt register).
- **short-term/once-off** otherwise - an isolated bad month against an
  otherwise healthy trend (a temporary price move, input-cost spike, or
  one-off event).
"""

from __future__ import annotations

PERSISTENT_RUN_THRESHOLD = 3
HIGH_DEBT_TO_REVENUE_RATIO = 1.0
LOW_MARGIN_PCT = 5.0

SHORT_TERM = "short_term"
LONG_TERM = "long_term"


def debt_to_revenue_ratio(debt_register: list[dict] | None, annual_revenue: float | None) -> float:
    if not annual_revenue:
        return 0.0
    outstanding = sum(float(loan.get("outstanding_balance") or 0) for loan in (debt_register or []))
    return outstanding / annual_revenue


def _run_lengths(statuses: list[str], target: str) -> list[int]:
    """Length of the consecutive run each index belongs to, for a given status."""
    lengths = [0] * len(statuses)
    i = 0
    while i < len(statuses):
        if statuses[i] != target:
            i += 1
            continue
        j = i
        while j < len(statuses) and statuses[j] == target:
            j += 1
        run_len = j - i
        for k in range(i, j):
            lengths[k] = run_len
        i = j
    return lengths


def classify_cashflow_entries(
    entries: list[dict],
    debt_register: list[dict] | None = None,
    annual_revenue: float | None = None,
    profit_margin: float | None = None,
) -> list[dict]:
    """Return a copy of `entries` (chronological) with a classification added
    to every deficit month: `classification` (short_term/long_term/None) and
    a plain-language `classification_reason`.
    """
    statuses = [e.get("cashflow_status") for e in entries]
    run_lengths = _run_lengths(statuses, "deficit")

    debt_ratio = debt_to_revenue_ratio(debt_register, annual_revenue)
    high_debt = debt_ratio >= HIGH_DEBT_TO_REVENUE_RATIO
    low_margin = profit_margin is not None and profit_margin < LOW_MARGIN_PCT

    classified: list[dict] = []
    for entry, run_len in zip(entries, run_lengths):
        updated = dict(entry)
        if entry.get("cashflow_status") != "deficit":
            updated["classification"] = None
            updated["classification_reason"] = ""
            classified.append(updated)
            continue

        reasons: list[str] = []
        structural = False
        if run_len >= PERSISTENT_RUN_THRESHOLD:
            structural = True
            reasons.append(f"part of a {run_len}-month run of consecutive cash-flow deficits")
        if high_debt:
            structural = True
            reasons.append(f"debt is high relative to revenue ({debt_ratio:.1f}x annual revenue)")
        if low_margin:
            structural = True
            reasons.append(f"profit margin is persistently low ({profit_margin:.1f}%)")

        if structural:
            updated["classification"] = LONG_TERM
            updated["classification_reason"] = "Long-term/structural — " + "; ".join(reasons) + "."
        else:
            updated["classification"] = SHORT_TERM
            updated["classification_reason"] = (
                "Short-term/once-off — an isolated month against an otherwise healthy trend."
            )
        classified.append(updated)
    return classified
