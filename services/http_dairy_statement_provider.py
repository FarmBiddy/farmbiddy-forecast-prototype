"""
Non-functional HTTP dairy statement provider skeleton.

This class exists to make the future replacement point for
``MockDairyStatementProvider`` explicit and concrete, per the architecture
described in ``docs/dairy_statement_integration.md``. It implements the same
method signature as ``DairyStatementProvider`` (see
``services/dairy_statement_provider.py``), so once implemented it could be
registered in ``services/dairy_statement_provider_factory.py`` and swapped
in for the mock without any change to the adapter or the financial engine.

This module makes NO network request and imports no HTTP client library.
Calling ``get_milk_statement`` always raises
``DairyStatementProviderNotConfiguredError`` — this class is a placeholder
for a future real implementation, not a working HTTP client.

Expected future response flow (not implemented yet):

1. Build a request to ``{base_url}/...`` for the given ``provider_id`` /
   ``supplier_no`` / ``invoice_id`` / ``month_no`` / ``year``.
2. Attach authentication using ``api_key`` (the exact mechanism — header,
   query param, bearer token, etc. — is defined by whatever real
   document-management service this eventually calls; it is not decided
   here).
3. Parse the HTTP JSON response with
   ``DairyStatementResponse.model_validate(...)``, reusing the exact same
   validation the mock provider's output already passes through today.
4. Return that ``DairyStatementResponse`` unchanged — the adapter and
   financial engine already accept it with no code changes required, by
   design (see the Phase 3 adapter and the provider protocol).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.dairy_statement import DairyStatementResponse


class DairyStatementProviderNotConfiguredError(NotImplementedError):
    """Raised by a provider skeleton that has no real implementation yet."""


@dataclass(frozen=True)
class HttpDairyStatementProviderConfig:
    """
    Configuration for a future ``HttpDairyStatementProvider``.

    Neither field defaults to a real value: ``base_url`` defaults to an
    empty string and ``api_key`` defaults to ``None``. Nothing in this
    module embeds a real service URL or a credential — both must be
    supplied explicitly by the caller (e.g. read from environment variables
    at the application's configuration layer; see
    ``docs/dairy_statement_integration.md`` for the placeholder variable
    names) before this provider could ever be used for anything real.
    """

    base_url: str = ""
    api_key: Optional[str] = None


class HttpDairyStatementProvider:
    """
    Future HTTP-backed implementation of the ``DairyStatementProvider`` protocol.

    Not implemented. Every call to ``get_milk_statement`` raises
    ``DairyStatementProviderNotConfiguredError`` regardless of configuration
    — this class exists only to make the future replacement point explicit,
    not to perform any real integration.
    """

    def __init__(self, config: HttpDairyStatementProviderConfig):
        if not isinstance(config, HttpDairyStatementProviderConfig):
            raise TypeError(
                "HttpDairyStatementProvider requires an "
                "HttpDairyStatementProviderConfig instance"
            )
        self._config = config

    def get_milk_statement(
        self,
        provider_id: str,
        supplier_no: str,
        invoice_id: str,
        month_no: int,
        year: int,
    ) -> DairyStatementResponse:
        raise DairyStatementProviderNotConfiguredError(
            "HttpDairyStatementProvider is a non-functional skeleton — no real "
            "HTTP integration exists yet. See the module docstring in "
            "services/http_dairy_statement_provider.py and "
            "docs/dairy_statement_integration.md for the intended future "
            "response flow."
        )
