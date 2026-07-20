"""
Dairy statement adapter.

Maps a normalised ``DairyStatementResponse`` (mock today, a real provider in
future — see ``services/dairy_statement_provider.py``) into the monthly-entry
shape consumed by ``services/multi_sector_farm.py``, i.e. one item of
``sectors.dairy.monthly[]`` in ``datasets/multi_sector_farm.json``:

    {
      "year": 2024, "month": 1, "period": "2024-01",
      "operational": {"milking_cows": ..., "milk_litres": ..., ...},
      "pricing": {"milk_price_per_litre": ...},
      "revenue": {"milk": ..., "cattle_sales": ..., ..., "total": ...},
      "costs": {"feed": ..., "vet": ..., ..., "total": ...},
    }

This is the *only* place in the whole dairy-statement feature where unit
conversion happens (pence-per-litre -> EUR-per-litre), and the only place
that reshapes provider data into the legacy engine's vocabulary. Nothing in
``forecast_engine/``, ``financial_engine/``, or ``services/multi_sector_farm.py``
is modified or needs to be — this module only produces a plain dict shaped
like the entries those modules already consume.

What this adapter deliberately does NOT do:
- It does not fabricate herd counts (``milking_cows``, ``calves``,
  ``dry_cows``) or a cost breakdown (``feed``, ``vet``, ``labour``, ...).
  A milk statement carries none of that data, so those fields are left out
  of ``operational``/``costs`` entirely rather than defaulted to 0 or an
  invented number. Consumers such as
  ``services.multi_sector_farm.aggregate_sector_financials`` already treat
  a missing key as 0 via ``dict.get(key, 0)``, so this is safe — but it is
  a real data gap, not a zero value, and callers merging this entry into a
  full farm record still need herd/cost data from elsewhere.
- It does not write to, or merge with, ``datasets/multi_sector_farm.json``.
  It returns a dict; what a caller does with that dict (append it to a
  sector's ``monthly`` list, persist it, etc.) is out of scope here.
- It does not touch ``revenue.cattle_sales`` / ``lamb_sales`` / ``wool`` /
  ``other`` beyond the required zeros — a dairy co-op statement has no
  opinion on beef or lamb income.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from models.dairy_statement import DairyStatementResponse

# The legacy engine has no currency field anywhere — every monetary value in
# datasets/multi_sector_farm.json is an implicit single currency. Converting
# a statement in any other currency would silently mix currencies, so only
# EUR is accepted for now.
_SUPPORTED_CURRENCY = "EUR"

# Pence-per-litre -> major-currency-unit-per-litre. 100 pence == 1 currency
# unit. This is the sole unit conversion in the dairy-statement feature,
# confined to this adapter as required by the Phase 1 contract design.
_PENCE_PER_CURRENCY_UNIT = Decimal("100")


class UnsupportedStatementCurrencyError(ValueError):
    """Raised when a statement's currency is not the one supported currency (EUR)."""


class IncompleteDairyStatementError(ValueError):
    """Raised when a statement is missing data this adapter must have to proceed."""


def _convert_ppl_to_currency_per_litre(price_ppl: Decimal) -> Decimal:
    """Convert a pence-per-litre price to major-currency-unit-per-litre."""
    return price_ppl / _PENCE_PER_CURRENCY_UNIT


def adapt_dairy_statement_to_monthly_entry(
    statement: DairyStatementResponse,
) -> Dict[str, Any]:
    """
    Map a normalised dairy statement into one dairy monthly-entry dict.

    Effective milk price is derived from ``pricing.gross_price_ppl`` (never
    ``base_price_ppl``), converted from pence-per-litre to
    currency-per-litre. ``pricing.total_payment`` is treated as authoritative
    statement data: it is used directly as ``revenue.milk`` /
    ``revenue.total`` rather than being recomputed from litres x price, so it
    is never overridden or double-counted against a derived figure.

    Quality metrics (``butterfat_percent``, ``protein_percent``,
    ``lactose_percent``, ``scc``, ``tbc``) are copied into a ``"quality"``
    key on the returned dict. No existing forecast, scenario, or dashboard
    calculation reads this key today, so it has no effect on any figure —
    it is kept available for a future consumer rather than discarded.

    Raises:
        UnsupportedStatementCurrencyError: if ``pricing.currency`` is not
            "EUR" — converting any other currency's pence-per-litre figure
            into this engine's implicit single currency would silently mix
            currencies.
        IncompleteDairyStatementError: if ``pricing.gross_price_ppl`` is
            ``None`` — there is no other field this adapter is allowed to
            substitute for the effective milk price.
    """
    pricing = statement.pricing

    if pricing.currency != _SUPPORTED_CURRENCY:
        raise UnsupportedStatementCurrencyError(
            f"Unsupported statement currency: {pricing.currency!r}. "
            f"This adapter only supports {_SUPPORTED_CURRENCY!r}, because the "
            f"existing financial engine has no currency field of its own."
        )

    if pricing.gross_price_ppl is None:
        raise IncompleteDairyStatementError(
            "pricing.gross_price_ppl is missing — cannot derive an effective "
            "milk price without it."
        )

    milk_price_per_litre = _convert_ppl_to_currency_per_litre(pricing.gross_price_ppl)
    milk_revenue = float(pricing.total_payment)
    period = statement.statement.period

    quality = statement.quality
    return {
        "year": period.year,
        "month": period.month,
        "period": f"{period.year:04d}-{period.month:02d}",
        "operational": {
            "milk_litres": float(statement.collections.total_litres),
        },
        "pricing": {
            "milk_price_per_litre": round(float(milk_price_per_litre), 4),
        },
        "revenue": {
            "milk": round(milk_revenue, 2),
            "cattle_sales": 0,
            "lamb_sales": 0,
            "wool": 0,
            "other": 0,
            "total": round(milk_revenue, 2),
        },
        # No cost breakdown exists in a milk statement — left empty rather
        # than defaulted, see module docstring.
        "costs": {},
        "quality": {
            "butterfat_percent": _decimal_to_float(quality.butterfat_percent),
            "protein_percent": _decimal_to_float(quality.protein_percent),
            "lactose_percent": _decimal_to_float(quality.lactose_percent),
            "scc": quality.scc,
            "tbc": quality.tbc,
        },
        "_source_statement": {
            "provider_id": statement.provider.id,
            "provider_name": statement.provider.name,
            "statement_id": statement.statement.statement_id,
            "currency": pricing.currency,
        },
    }


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    """Preserve ``None`` (unknown) rather than coercing it to 0.0."""
    return float(value) if value is not None else None
