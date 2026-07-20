"""
Dairy statement provider abstraction.

This module defines the seam between callers that need a dairy statement and
whatever actually supplies one. Today the only implementation is a mock
(``services/mock_dairy_statement_provider.py``); in future a real
HTTP-backed provider can implement the same ``DairyStatementProvider``
protocol and be substituted in without changing any caller.

Scope of this module:
- The provider contract (a ``typing.Protocol``) only.
- One exception type for a provider_id with no registered implementation.

No provider implementation, adapter, or HTTP endpoint lives here.
"""

from __future__ import annotations

from typing import Protocol

from models.dairy_statement import DairyStatementResponse


class UnsupportedDairyProviderError(ValueError):
    """Raised when a requested provider_id has no registered implementation."""


class DairyStatementProvider(Protocol):
    """
    Contract for retrieving a single dairy statement.

    Any implementation — mock or real — must:
    - Be synchronous (``def``, not ``async def``), matching the convention
      used everywhere else in ``services/`` and ``api/``.
    - Return a validated ``DairyStatementResponse``, never a raw dict.
    - Raise ``UnsupportedDairyProviderError`` for a ``provider_id`` it does
      not support, rather than returning a partial or empty response.
    """

    def get_milk_statement(
        self,
        provider_id: str,
        supplier_no: str,
        invoice_id: str,
        month_no: int,
        year: int,
    ) -> DairyStatementResponse:
        """Retrieve one dairy statement for the given supplier and period."""
        ...
