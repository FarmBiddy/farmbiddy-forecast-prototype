"""
Shell integration: capability registry.

This module maps stable `capability_key` strings (discoverable by clients)
to handler functions that delegate to existing service functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from identity.context import RequestIdentity
from services.document_service import get_document, list_documents
from services.financial_record_service import (
    category_choices_payload,
    find_possible_duplicate,
    get_financial_record,
    list_financial_records,
)
from services.category_budget_service import (
    get_category_budget,
    list_category_budgets,
)
from services.farmer_dashboard_service import (
    get_farmer_dashboard_preview,
)
from services.income_expense_service import build_income_expense_summary

# Access control helpers live in identity/access.py. We keep enforcement
# logic in the handler so the dispatcher stays generic.
from identity.access import enforce_farm_access


HandlerFn = Callable[
    [str, List[str], Dict[str, Any], RequestIdentity],
    Dict[str, Any],
]


@dataclass(frozen=True)
class CapabilityDefinition:
    key: str
    description: str
    required_params: Set[str]
    optional_params: Set[str]
    handler: HandlerFn


def _handle_dashboard_preview(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    _identity: RequestIdentity,
) -> Dict[str, Any]:
    # Existing service resolves any other defaults internally.
    # Params are reserved for future policy options.
    _ = params
    return get_farmer_dashboard_preview(farm_file, sectors=sectors)


def _handle_income_expenses_summary(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    _identity: RequestIdentity,
) -> Dict[str, Any]:
    months = int(params.get("months") or 12)
    return build_income_expense_summary(farm_file=farm_file, sectors=sectors, months=months)


def _handle_documents_list(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    # Matches existing /farmer/documents behaviour: enforce farm access.
    enforce_farm_access(identity, farm_file)

    document_type = params.get("document_type")
    payment_status = params.get("payment_status")

    documents = list_documents(
        farm_file,
        sectors=sectors,
        document_type=document_type,
        payment_status=payment_status,
    )
    return {
        "success": True,
        "farm_file": farm_file,
        "documents": documents,
        "count": len(documents),
    }


def _handle_records_list(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    enforce_farm_access(identity, farm_file)

    records = list_financial_records(
        farm_file,
        sectors=sectors,
        record_type=params.get("record_type"),
        category=params.get("category"),
    )
    return {
        "success": True,
        "farm_file": farm_file,
        "records": records,
        "count": len(records),
    }


def _handle_records_get(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    enforce_farm_access(identity, farm_file)
    record_id = str(params["record_id"])
    record = get_financial_record(farm_file, record_id)
    return {"success": True, "farm_file": farm_file, "record": record}


def _handle_records_duplicate_check(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    enforce_farm_access(identity, farm_file)

    possible_duplicate = find_possible_duplicate(
        farm_file,
        {
            "record_type": params["record_type"],
            "date": params["date"],
            "category": params["category"],
            "amount": float(params["amount"]),
        },
    )
    return {
        "success": True,
        "farm_file": farm_file,
        "possible_duplicate": possible_duplicate is not None,
        "duplicate_of": possible_duplicate,
    }


def _handle_documents_get(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    enforce_farm_access(identity, farm_file)
    document_id = str(params["document_id"])
    document = get_document(farm_file, document_id)
    return {"success": True, "farm_file": farm_file, "document": document}


def _handle_budgets_list(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    enforce_farm_access(identity, farm_file)

    budgets = list_category_budgets(
        farm_file,
        sectors=sectors,
        record_type=params.get("record_type"),
        category=params.get("category"),
        year=params.get("year"),
    )
    return {
        "success": True,
        "farm_file": farm_file,
        "budgets": budgets,
        "count": len(budgets),
    }


def _handle_budgets_get(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    enforce_farm_access(identity, farm_file)
    budget_id = str(params["budget_id"])
    budget = get_category_budget(farm_file, budget_id)
    return {"success": True, "farm_file": farm_file, "budget": budget}


def _handle_category_choices(
    farm_file: str,
    sectors: List[str],
    params: Dict[str, Any],
    identity: RequestIdentity,
) -> Dict[str, Any]:
    # Vocabulary is global (income/expense categories), no farm membership
    # required for read access.
    _ = farm_file, sectors, params, identity
    income, expenses = category_choices_payload()
    return {"success": True, "income_categories": income, "expense_categories": expenses}


CAPABILITIES: Dict[str, CapabilityDefinition] = {
    "dashboard.preview": CapabilityDefinition(
        key="dashboard.preview",
        description="Dashboard KPIs + profile preview (read-only).",
        required_params=set(),
        optional_params=set(),
        handler=_handle_dashboard_preview,
    ),
    "income_expenses.summary": CapabilityDefinition(
        key="income_expenses.summary",
        description="Income & Expenses summary by category (read-only).",
        required_params=set(),
        optional_params=set(),
        handler=_handle_income_expenses_summary,
    ),
    "documents.list": CapabilityDefinition(
        key="documents.list",
        description="List invoices/receipts (read-only, farm-scoped).",
        required_params=set(),
        optional_params=set(),
        handler=_handle_documents_list,
    ),

    # ── Reconciliation: Financial records ─────────────────────────────
    "records.list": CapabilityDefinition(
        key="records.list",
        description="List manually entered income/expense records.",
        required_params=set(),
        optional_params={"record_type", "category"},
        handler=_handle_records_list,
    ),
    "records.get": CapabilityDefinition(
        key="records.get",
        description="Fetch one financial record by id.",
        required_params={"record_id"},
        optional_params=set(),
        handler=_handle_records_get,
    ),
    "records.duplicate_check": CapabilityDefinition(
        key="records.duplicate_check",
        description="Return a possible duplicate hint for a proposed record.",
        required_params={"record_type", "date", "category", "amount"},
        optional_params=set(),
        handler=_handle_records_duplicate_check,
    ),

    # ── Reconciliation: Documents ─────────────────────────────────────
    "documents.get": CapabilityDefinition(
        key="documents.get",
        description="Fetch one invoice/receipt document by id.",
        required_params={"document_id"},
        optional_params=set(),
        handler=_handle_documents_get,
    ),

    # ── Reconciliation: Budgets ──────────────────────────────────────
    "budgets.list": CapabilityDefinition(
        key="budgets.list",
        description="List category budgets (monthly) with optional filters.",
        required_params=set(),
        optional_params={"record_type", "category", "year"},
        handler=_handle_budgets_list,
    ),
    "budgets.get": CapabilityDefinition(
        key="budgets.get",
        description="Fetch one category budget by id.",
        required_params={"budget_id"},
        optional_params=set(),
        handler=_handle_budgets_get,
    ),

    # ── Vocabulary / vocabulary helpers ────────────────────────────────
    "vocabulary.category_choices": CapabilityDefinition(
        key="vocabulary.category_choices",
        description="Return income and expense category vocabulary.",
        required_params=set(),
        optional_params=set(),
        handler=_handle_category_choices,
    ),
}


def list_capabilities() -> List[Dict[str, Any]]:
    """Return JSON-serialisable capability metadata for discovery."""
    payload: List[Dict[str, Any]] = []
    for cap in CAPABILITIES.values():
        payload.append(
            {
                "key": cap.key,
                "description": cap.description,
                "required_params": sorted(list(cap.required_params)),
                "optional_params": sorted(list(cap.optional_params)),
            }
        )
    payload.sort(key=lambda x: x["key"])
    return payload


def get_capability(key: str) -> Optional[CapabilityDefinition]:
    return CAPABILITIES.get(key)

