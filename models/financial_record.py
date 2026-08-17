"""
Generic financial-record domain model (P0.2 / P1.2).

A `FinancialRecord` is the one shape every farm money-in or money-out event
funnels through, however it originates:

    manual entry -> FinancialRecord
    invoice/receipt (P1.2) -> FinancialRecord
    OCR (future) -> FinancialRecord
    bank feed (future) -> FinancialRecord
    accounting integration (future) -> FinancialRecord

This keeps category aggregation, Income & Expenses, Budget vs Actual, and
alerts all reading from one consistent shape instead of each origin type
inventing its own. Categories are intentionally sector-agnostic and farmer-
facing (Milk, Feed, Vet, ...) rather than tied to Dairy-only fields, per the
product principle that FarmBiddy must not hard-code Dairy assumptions into
generic domain logic. Sector-specific detail (e.g. a beef vs dairy feed
split) is an optional tag on top of this generic shape, not a separate model.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

RECORD_TYPES = ("income", "expense")
ORIGIN_TYPES = ("manual", "document", "import", "bank_feed")

INCOME_CATEGORIES: list[dict[str, str]] = [
    {"id": "milk", "label": "Milk"},
    {"id": "livestock", "label": "Livestock"},
    {"id": "crops", "label": "Crops"},
    {"id": "grants_schemes", "label": "Grants / Schemes"},
    {"id": "contract_work", "label": "Contract Work"},
    {"id": "other_income", "label": "Other Farm Income"},
]

EXPENSE_CATEGORIES: list[dict[str, str]] = [
    {"id": "feed", "label": "Feed"},
    {"id": "fertiliser", "label": "Fertiliser"},
    {"id": "veterinary", "label": "Veterinary"},
    {"id": "contractor", "label": "Contractor"},
    {"id": "machinery", "label": "Machinery"},
    {"id": "fuel", "label": "Fuel"},
    {"id": "labour", "label": "Labour"},
    {"id": "insurance", "label": "Insurance"},
    {"id": "loan_repayments", "label": "Loan Repayments"},
    {"id": "utilities", "label": "Utilities"},
    {"id": "other_expense", "label": "Other"},
]

_CATEGORIES_BY_TYPE = {"income": INCOME_CATEGORIES, "expense": EXPENSE_CATEGORIES}
_LABEL_BY_ID = {
    record_type: {c["id"]: c["label"] for c in categories}
    for record_type, categories in _CATEGORIES_BY_TYPE.items()
}


def category_choices(record_type: str) -> list[dict[str, str]]:
    """Category vocabulary for a record type, for populating UI dropdowns."""
    return list(_CATEGORIES_BY_TYPE.get(record_type, []))


def is_valid_category(record_type: str, category_id: str) -> bool:
    return category_id in _LABEL_BY_ID.get(record_type, {})


def category_label(record_type: str, category_id: str) -> str:
    return _LABEL_BY_ID.get(record_type, {}).get(category_id, category_id.replace("_", " ").title())


class FinancialRecordCreate(BaseModel):
    """Fields a farmer (or a future document/import origin) supplies for one record."""

    record_type: Literal["income", "expense"]
    date: str = Field(..., description="ISO date, e.g. 2026-03-15")
    category: str
    amount: float = Field(..., gt=0, description="Always positive; sign is implied by record_type")
    description: str = Field(..., min_length=1, max_length=200)
    counterparty: Optional[str] = Field(
        default=None, max_length=120,
        description="Customer/source for income, or supplier for an expense",
    )
    notes: Optional[str] = Field(default=None, max_length=1000)
    sector: Optional[str] = Field(default=None, description="dairy/beef/lamb, or omitted for whole-farm/household")

    @field_validator("category")
    @classmethod
    def _category_known(cls, value: str, info) -> str:
        record_type = info.data.get("record_type")
        if record_type and not is_valid_category(record_type, value):
            valid = ", ".join(c["id"] for c in category_choices(record_type))
            raise ValueError(f"Unknown {record_type} category '{value}'. Valid options: {valid}")
        return value

    @field_validator("date")
    @classmethod
    def _date_looks_like_iso(cls, value: str) -> str:
        parts = value.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("date must be in YYYY-MM-DD format")
        return value


class FinancialRecordUpdate(BaseModel):
    """Partial update — only manual, farmer-editable fields can change.

    `record_type`, `origin`, and `origin_document_id` are intentionally not
    editable here: changing what a record *is* or where it came from is a
    delete-and-recreate, not an edit, so the audit trail stays honest.
    """

    date: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, min_length=1, max_length=200)
    counterparty: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)
    sector: Optional[str] = None


class FinancialRecord(FinancialRecordCreate):
    """A stored financial record, with identity, provenance, and timestamps."""

    id: str
    farm_file: str
    origin: Literal["manual", "document", "import", "bank_feed"] = "manual"
    origin_document_id: Optional[str] = None
    created_at: str
    updated_at: str


class FinancialRecordResponse(BaseModel):
    success: bool = True
    record: FinancialRecord
    possible_duplicate: bool = False
    duplicate_of: Optional[str] = None


class FinancialRecordListResponse(BaseModel):
    success: bool = True
    farm_file: str
    records: list[FinancialRecord] = Field(default_factory=list)
    count: int = 0


class FinancialRecordDeleteResponse(BaseModel):
    success: bool = True
    deleted_id: str


class CategoryTotal(BaseModel):
    category_id: str
    label: str
    total: float
    count: int = 0


class IncomeExpenseSummaryResponse(BaseModel):
    success: bool = True
    farm_name: str
    selected_sectors: list[str] = Field(default_factory=list)
    period: dict[str, Any] = Field(default_factory=dict)
    income_total: float = 0
    expense_total: float = 0
    difference: float = 0
    income_categories: list[CategoryTotal] = Field(default_factory=list)
    expense_categories: list[CategoryTotal] = Field(default_factory=list)
    manual_income_total: float = 0
    manual_expense_total: float = 0
    manual_records: list[FinancialRecord] = Field(default_factory=list)
    income_category_choices: list[dict[str, str]] = Field(default_factory=list)
    expense_category_choices: list[dict[str, str]] = Field(default_factory=list)
