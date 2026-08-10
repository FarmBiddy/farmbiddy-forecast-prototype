"""
Practical cash-flow action testing (Teagasc item 6).

Each action is a pure transformation of a `combined_cashflow`/
`combined_running_balance` monthly forecast (built by
services/multi_sector_farm.py, Phase 2/3 of the Teagasc review): it shifts
(or, for short-term credit, temporarily injects) cash between months, then
recomputes the running balance so the resulting lowest cash balance and
number of deficit months can be reported.

Shifting cash between months is zero-sum over the year, so these actions
change *when* the low point falls, not the underlying annual total - a
genuinely useful signal in itself: if none of the 5 actions meaningfully
raise the lowest balance, that corroborates a long-term/structural problem
(Phase 4) rather than a timing issue. When auto-detecting a month to move
cash to/from, only months *later* in the 12-month forecast window are
considered valid sources/destinations (you can only defer into the future,
or bring forward from it) - if none exists, the action reports that it has
no effect within this forecast window rather than guessing.
"""

from __future__ import annotations

BRING_FORWARD_SALES = "bring_forward_sales"
DEFER_PURCHASES = "defer_purchases"
ADJUST_LOAN_TIMING = "adjust_loan_timing"
MATCH_PAYMENTS_TO_SURPLUS = "match_payments_to_surplus"
USE_SHORT_TERM_CREDIT = "use_short_term_credit"

ACTION_LABELS = {
    BRING_FORWARD_SALES: "Bring forward sales",
    DEFER_PURCHASES: "Defer purchases/expenditure",
    ADJUST_LOAN_TIMING: "Change loan-repayment timing",
    MATCH_PAYMENTS_TO_SURPLUS: "Match large payments to surplus months",
    USE_SHORT_TERM_CREDIT: "Use short-term credit for temporary gaps",
}

ALL_ACTIONS = tuple(ACTION_LABELS.keys())

DEFAULT_SHORT_TERM_CREDIT_RATE = 8.0  # annual %, one month of interest charged
DEFAULT_NOMINAL_AMOUNT = 1000.0

NO_LATER_MONTH_MESSAGE = (
    "No later month is available within the 12-month forecast, so this action "
    "has no effect here — the shortfall would need to be addressed another way."
)


def _recompute_running_balance(months: list[dict]) -> list[dict]:
    """Recompute `combined_running_balance` after `combined_cashflow` edits."""
    if not months:
        return []
    opening = months[0]["combined_running_balance"] - months[0]["combined_cashflow"]
    running = opening
    result = []
    for month in months:
        updated = dict(month)
        running += updated["combined_cashflow"]
        updated["combined_running_balance"] = round(running, 2)
        result.append(updated)
    return result


def lowest_balance_and_deficits(months: list[dict]) -> dict:
    """Headline metrics the document asks every action to report."""
    if not months:
        return {"lowest_balance": 0.0, "lowest_balance_month": None, "deficit_months": 0}
    worst = min(months, key=lambda m: m["combined_running_balance"])
    deficit_months = sum(1 for m in months if m["combined_running_balance"] < 0)
    return {
        "lowest_balance": worst["combined_running_balance"],
        "lowest_balance_month": worst["month"],
        "deficit_months": deficit_months,
    }


def _index_of_month(months: list[dict], month: int) -> int | None:
    for i, m in enumerate(months):
        if m["month"] == month:
            return i
    return None


def _months_after(months: list[dict], month: int) -> list[dict]:
    """Months later in the 12-month forecast window than `month`."""
    idx = _index_of_month(months, month)
    if idx is None:
        return []
    return months[idx + 1:]


def _lowest_balance_month_entry(months: list[dict]) -> dict:
    return min(months, key=lambda m: m["combined_running_balance"])


def _best_cashflow_month(candidates: list[dict]) -> dict | None:
    return max(candidates, key=lambda m: m["combined_cashflow"]) if candidates else None


def _default_amount(months: list[dict], month: int) -> float:
    """A realistic single-month cash-movement default: this month's own net
    cash flow magnitude, rather than the whole year's cumulative shortfall."""
    entry = next((m for m in months if m["month"] == month), None)
    if not entry:
        return DEFAULT_NOMINAL_AMOUNT
    amount = abs(entry.get("combined_cashflow") or 0)
    return round(amount, 2) if amount else DEFAULT_NOMINAL_AMOUNT


def _shift_cash(months: list[dict], amount: float, out_month: int, in_month: int) -> list[dict]:
    """Move `amount` of cash flow away from `out_month` into `in_month`."""
    shifted = [dict(m) for m in months]
    for m in shifted:
        if m["month"] == out_month:
            m["combined_cashflow"] = round(m["combined_cashflow"] - amount, 2)
        if m["month"] == in_month:
            m["combined_cashflow"] = round(m["combined_cashflow"] + amount, 2)
    return _recompute_running_balance(shifted)


def apply_bring_forward_sales(
    months: list[dict],
    amount: float | None = None,
    from_month: int | None = None,
    to_month: int | None = None,
) -> tuple[list[dict], str]:
    """Bring forward expected sales from a later month into the tight month."""
    problem = _lowest_balance_month_entry(months)
    to_month = to_month or problem["month"]

    if from_month is None:
        source = _best_cashflow_month(_months_after(months, to_month))
        if source is None:
            return [dict(m) for m in months], NO_LATER_MONTH_MESSAGE
        from_month = source["month"]

    amount = amount if amount is not None else _default_amount(months, from_month)
    scenario = _shift_cash(months, amount, out_month=from_month, in_month=to_month)
    description = (
        f"Bring forward €{amount:,.0f} of expected sales from month {from_month} "
        f"into month {to_month}."
    )
    return scenario, description


def _resolve_deferral(
    months: list[dict],
    amount: float | None,
    from_month: int | None,
    to_month: int | None,
) -> tuple[list[dict] | None, float | None, int | None, int | None]:
    """Shared resolution logic for deferring an expense out of the tight month
    into a later month. Returns (None, None, None, None) when no later month
    is available and `to_month` wasn't given explicitly."""
    problem = _lowest_balance_month_entry(months)
    from_month = from_month or problem["month"]

    if to_month is None:
        destination = _best_cashflow_month(_months_after(months, from_month))
        if destination is None:
            return None, None, None, None
        to_month = destination["month"]

    amount = amount if amount is not None else _default_amount(months, from_month)
    scenario = _shift_cash(months, amount, out_month=to_month, in_month=from_month)
    return scenario, amount, from_month, to_month


def apply_defer_purchases(
    months: list[dict],
    amount: float | None = None,
    from_month: int | None = None,
    to_month: int | None = None,
) -> tuple[list[dict], str]:
    """Defer a purchase/expense out of the tight month into a later month."""
    scenario, amount, from_month, to_month = _resolve_deferral(months, amount, from_month, to_month)
    if scenario is None:
        return [dict(m) for m in months], NO_LATER_MONTH_MESSAGE
    description = (
        f"Defer €{amount:,.0f} of expenditure from month {from_month} to month {to_month}."
    )
    return scenario, description


def apply_adjust_loan_timing(
    months: list[dict],
    amount: float | None = None,
    from_month: int | None = None,
    to_month: int | None = None,
) -> tuple[list[dict], str]:
    """Move a loan repayment to a different month (same mechanic as deferring
    an expense, but framed around a specific loan instalment)."""
    scenario, amount, from_month, to_month = _resolve_deferral(months, amount, from_month, to_month)
    if scenario is None:
        return [dict(m) for m in months], NO_LATER_MONTH_MESSAGE
    description = (
        f"Move €{amount:,.0f} of loan repayment from month {from_month} to month {to_month}."
    )
    return scenario, description


def apply_match_payments_to_surplus(
    months: list[dict],
    amount: float | None = None,
    payment_month: int | None = None,
    to_month: int | None = None,
) -> tuple[list[dict], str]:
    """Move a large planned payment out of the tight month into the best surplus month."""
    scenario, amount, payment_month, to_month = _resolve_deferral(months, amount, payment_month, to_month)
    if scenario is None:
        return [dict(m) for m in months], NO_LATER_MONTH_MESSAGE
    description = (
        f"Move a €{amount:,.0f} payment from month {payment_month} to the strongest "
        f"surplus month available (month {to_month})."
    )
    return scenario, description


def apply_use_short_term_credit(
    months: list[dict],
    amount: float | None = None,
    draw_month: int | None = None,
    repay_month: int | None = None,
    annual_rate: float | None = None,
) -> tuple[list[dict], str]:
    """Draw short-term credit to cover a temporary gap, repaid with interest
    later. If no later month exists within the forecast window, the draw is
    left outstanding (to be repaid beyond the 12-month horizon) rather than
    repaid out of order."""
    problem = _lowest_balance_month_entry(months)
    draw_month = draw_month or problem["month"]

    repay_available = True
    if repay_month is None:
        destination = _best_cashflow_month(_months_after(months, draw_month))
        if destination is None:
            repay_available = False
        else:
            repay_month = destination["month"]

    if amount is not None:
        resolved_amount = amount
    else:
        gap = -problem["combined_running_balance"]
        resolved_amount = round(gap, 2) if gap > 0 else _default_amount(months, draw_month)
    rate = annual_rate if annual_rate is not None else DEFAULT_SHORT_TERM_CREDIT_RATE

    scenario = [dict(m) for m in months]
    for m in scenario:
        if m["month"] == draw_month:
            m["combined_cashflow"] = round(m["combined_cashflow"] + resolved_amount, 2)
    if repay_available:
        interest = round(resolved_amount * (rate / 100) / 12, 2)
        for m in scenario:
            if m["month"] == repay_month:
                m["combined_cashflow"] = round(m["combined_cashflow"] - resolved_amount - interest, 2)
    scenario = _recompute_running_balance(scenario)

    if repay_available:
        description = (
            f"Draw €{resolved_amount:,.0f} of short-term credit in month {draw_month} to cover "
            f"the gap, repaid with €{interest:,.0f} interest in month {repay_month}."
        )
    else:
        description = (
            f"Draw €{resolved_amount:,.0f} of short-term credit in month {draw_month} to cover "
            "the gap. No later month remains in this 12-month forecast to repay it — it would "
            "carry forward as an outstanding balance beyond this window."
        )
    return scenario, description


ACTION_FUNCTIONS = {
    BRING_FORWARD_SALES: apply_bring_forward_sales,
    DEFER_PURCHASES: apply_defer_purchases,
    ADJUST_LOAN_TIMING: apply_adjust_loan_timing,
    MATCH_PAYMENTS_TO_SURPLUS: apply_match_payments_to_surplus,
    USE_SHORT_TERM_CREDIT: apply_use_short_term_credit,
}


def apply_cashflow_action(action: str, months: list[dict], **params) -> tuple[list[dict], str]:
    """Dispatch to the requested action function by id."""
    func = ACTION_FUNCTIONS.get(action)
    if not func:
        raise ValueError(f"Unknown cash-flow action: {action}")
    return func(months, **params)
