"""
Category-level budget domain model (P0.3).

A `CategoryBudget` is a farmer-set monthly spending/income target for one
category from the same vocabulary as `models.financial_record`
(Feed, Milk, Vet, ...). It is a deliberately separate model from:

  * the dataset's existing whole-farm `cash_flow_budget` entries
    (services/cashflow_budget_service.py, Teagasc items 1-2) - that
    compares one combined cash-in/cash-out figure per month; this compares
    individual categories so a farmer can see *which* category is driving
    a variance ("Feed EUR120 above budget"), and
  * Actuals (models.financial_record / services.financial_record_service) -
    a budget number is a plan, never a transaction, and the two are never
    merged into one figure.

Monthly records are the one canonical stored shape. "Annual" entry is
only ever a UX convenience at creation time (see
`CategoryBudgetAnnualCreate`): the service splits the annual figure into
12 monthly records and tags them with a visible `allocation_rule` so it is
always traceable how a monthly number was derived, never silently
invented.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from models.financial_record import is_valid_category

BUDGET_SOURCES = ("monthly", "annual_allocation")


class CategoryBudgetMonthlyCreate(BaseModel):
    """Set (or replace) the budget for one category in one specific month."""

    record_type: Literal["income", "expense"]
    category: str
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    amount: float = Field(..., ge=0, description="Budgeted amount for this category this month")
    sector: Optional[str] = Field(
        default=None,
        description="dairy/beef/lamb to scope this budget to one sector, or omitted for whole-farm",
    )
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("category")
    @classmethod
    def _category_known(cls, value: str, info) -> str:
        record_type = info.data.get("record_type")
        if record_type and not is_valid_category(record_type, value):
            raise ValueError(f"Unknown {record_type} category '{value}'.")
        return value


class CategoryBudgetAnnualCreate(BaseModel):
    """Convenience entry: one annual figure, split evenly across 12 months.

    The split is an explicit, visible allocation rule (`even_12`), not a
    hidden estimate - every resulting monthly record records the original
    `annual_total` and the rule used, so the farmer can always see how the
    monthly number was derived and adjust an individual month afterwards.
    """

    record_type: Literal["income", "expense"]
    category: str
    year: int = Field(..., ge=2000, le=2100)
    annual_amount: float = Field(..., ge=0, description="Total budgeted amount for the full calendar year")
    sector: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("category")
    @classmethod
    def _category_known(cls, value: str, info) -> str:
        record_type = info.data.get("record_type")
        if record_type and not is_valid_category(record_type, value):
            raise ValueError(f"Unknown {record_type} category '{value}'.")
        return value


class CategoryBudgetUpdate(BaseModel):
    """A budget is a farmer-adjustable plan figure - only the amount/notes
    can change. Category, record_type, year, and month identify *which*
    budget slot this is; changing those is delete-and-recreate."""

    amount: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=1000)


class CategoryBudget(BaseModel):
    """A stored monthly category budget record."""

    id: str
    farm_file: str
    sector: Optional[str] = None
    record_type: Literal["income", "expense"]
    category: str
    year: int
    month: int
    amount: float
    source: Literal["monthly", "annual_allocation"] = "monthly"
    annual_total: Optional[float] = Field(
        default=None, description="Set only when source == annual_allocation: the original annual figure entered",
    )
    allocation_rule: Optional[str] = Field(
        default=None, description="e.g. 'even_12' - how amount was derived from annual_total",
    )
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class CategoryBudgetResponse(BaseModel):
    success: bool = True
    budgets: list[CategoryBudget] = Field(default_factory=list)


class CategoryBudgetListResponse(BaseModel):
    success: bool = True
    farm_file: str
    budgets: list[CategoryBudget] = Field(default_factory=list)
    count: int = 0


class CategoryBudgetDeleteResponse(BaseModel):
    success: bool = True
    deleted_id: str


class CategoryVarianceRow(BaseModel):
    """One category's Budget vs Actual comparison over the reported window."""

    record_type: Literal["income", "expense"]
    category_id: str
    label: str
    status: Literal["no_budget_set", "on_budget", "above_budget", "below_budget", "ahead", "behind"]
    budget_total: Optional[float] = None
    actual_total: Optional[float] = None
    difference: Optional[float] = None
    months_with_budget: int = 0
    months_in_window: int = 0
    summary: str = ""


class CategoryBudgetVsActualResponse(BaseModel):
    success: bool = True
    farm_name: str
    selected_sectors: list[str] = Field(default_factory=list)
    period: dict = Field(default_factory=dict)
    months_in_window: int = 0
    overall_status: Literal["no_budget_set", "on_budget", "ahead", "behind"] = "no_budget_set"
    overall_budget_total: Optional[float] = None
    overall_actual_total: Optional[float] = None
    overall_difference: Optional[float] = None
    overall_summary: str = ""
    top_contributors: list[CategoryVarianceRow] = Field(default_factory=list)
    categories: list[CategoryVarianceRow] = Field(default_factory=list)
    unbudgeted_categories: list[CategoryVarianceRow] = Field(default_factory=list)
