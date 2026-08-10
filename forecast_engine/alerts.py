def generate_alerts(
    farm,
    profit,
    revenue,
    costs,
    monthly_cashflow,
    monthly_forecast=None,
    debt_register=None,
):
    alerts = []

    opening_balance = farm.get("opening_cash_balance", 0)
    ending_balance = opening_balance + profit
    monthly_costs = costs / 12
    min_balance = min(opening_balance, ending_balance)

    if profit < 0:
        alerts.append("Negative profit: The farm is forecasted to make a loss.")

    if revenue > 0:
        profit_margin = profit / revenue

        if profit_margin < 0.15:
            alerts.append("Low profit margin: Margin is below 15%.")

        feed_cost_pct = farm["feed"] / revenue

        if feed_cost_pct > 0.35:
            alerts.append(
                "High feed cost percentage: Feed exceeds 35% of revenue."
            )

    if monthly_cashflow < 0:
        alerts.append(
            "Negative monthly cashflow: Monthly income does not cover monthly costs."
        )

    if min_balance < monthly_costs:
        alerts.append(
            "Low cash balance: Cash balance falls below one month of operating costs."
        )

    if monthly_forecast:
        alerts.extend(generate_early_cashflow_warnings(monthly_forecast, debt_register))

    return alerts


def _monthly_balance_series(monthly_forecast):
    """Normalise a monthly forecast into (month, balance, household_outgoings) triples.

    Prefers the farm+household combined figures added in Phase 2
    (`combined_running_balance`) when present, falling back to the legacy
    farm-only `running_balance` field for callers that don't have a
    household split.
    """
    series = []
    for entry in monthly_forecast or []:
        balance = entry.get("combined_running_balance")
        if balance is None:
            balance = entry.get("running_balance")
        household_outgoings = entry.get("household_outgoings")
        series.append({
            "month": entry.get("month"),
            "balance": float(balance or 0),
            "household_outgoings": float(household_outgoings) if household_outgoings is not None else None,
        })
    return series


def _loan_monthly_total(debt_register):
    return sum(float(loan.get("monthly_repayment") or 0) for loan in (debt_register or []))


def generate_early_cashflow_warnings(monthly_forecast, debt_register=None):
    """Month-by-month early-warning scan over the forecast (Teagasc item 7).

    Flags, in order of how the document describes them:
    - future months where the projected balance goes negative;
    - an increasing/widening overdraft (3+ consecutive months getting worse);
    - a month where the balance would not cover that month's own fixed
      recurring outgoings (loan repayments + household costs);
    - loan repayments landing in a month where cash is already low.

    "Increasing merchant/credit-card balances" from the source document is
    intentionally not implemented: the dataset and household model
    (Phase 2) have no such field, so there is nothing to scan.
    """
    series = _monthly_balance_series(monthly_forecast)
    if not series:
        return []

    warnings = []
    loan_monthly_total = _loan_monthly_total(debt_register)

    negative_months = [m["month"] for m in series if m["balance"] < 0]
    if negative_months:
        first, last = negative_months[0], negative_months[-1]
        span = f"month {first}" if first == last else f"months {first}-{last}"
        warnings.append(
            f"Cash-flow warning: the forecast shows a negative cash balance in {span} "
            f"({len(negative_months)} month(s) in total) — plan for the shortfall before it arrives."
        )

    worst_run_start, worst_run_len = None, 0
    run_start, run_len = None, 0
    prev_balance = None
    for m in series:
        if m["balance"] < 0:
            if run_len > 0 and prev_balance is not None and m["balance"] <= prev_balance:
                run_len += 1
            else:
                run_start, run_len = m["month"], 1
        else:
            run_start, run_len = None, 0
        if run_len > worst_run_len:
            worst_run_len, worst_run_start = run_len, run_start
        prev_balance = m["balance"]
    if worst_run_len >= 3:
        warnings.append(
            f"Increasing overdraft use: cash balance has worsened for {worst_run_len} consecutive "
            f"months starting month {worst_run_start} — the shortfall is widening, not stabilising."
        )

    for m in series:
        fixed_outgoings = loan_monthly_total + (m["household_outgoings"] or 0)
        if fixed_outgoings > 0 and m["balance"] < fixed_outgoings:
            warnings.append(
                f"Insufficient cash for direct debits: month {m['month']}'s projected balance "
                f"(€{m['balance']:,.0f}) would not cover that month's fixed outgoings "
                f"(€{fixed_outgoings:,.0f}) such as loan repayments and household costs."
            )
            break

    if loan_monthly_total > 0:
        for m in series:
            if 0 <= m["balance"] < loan_monthly_total * 2:
                warnings.append(
                    f"Loan repayments due in a low-cash month: month {m['month']} has about "
                    f"€{loan_monthly_total:,.0f} of loan repayments due while the projected balance "
                    f"is only €{m['balance']:,.0f}."
                )
                break

    return warnings
