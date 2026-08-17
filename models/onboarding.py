"""
Simple Farmer Onboarding domain model (P1.3).

A low-friction, one-screen setup flow for a farmer who has not yet
recorded anything: farm type, main expected income, main costs, loans/
repayments, and current cash. It deliberately does NOT invent a new
financial-fact store - every input maps onto a model that already exists
and is already tested:

    Main expected income / Main costs -> category-level annual budgets
        (models.category_budget / services.category_budget_service),
        so the farmer sees a Budget vs Actual baseline the moment they
        start recording real transactions - no fabricated Actuals.
    Current cash                      -> a farmer-declared override of
        `opening_cash_balance`, applied in
        `services.multi_sector_farm.to_legacy_farm_dict` (the one place
        that value already flows from for every dashboard/forecast
        figure), so it reaches the whole existing tested pipeline
        through a single, well-understood injection point rather than a
        second parallel "current cash" concept.
    Farm type                         -> a descriptive label, plus a
        best-effort mapping onto the sectors the forecast engine already
        models (dairy/beef/sheep -> lamb). Farm types the engine does not
        model (Suckler, Tillage, Mixed, Other) are stored and surfaced
        as-is - onboarding never pretends to forecast a sector that has
        no supporting model, and never hard-codes Dairy-specific
        behaviour into this generic layer.

Loans/repayments are intentionally NOT written into the dataset's
per-lender Debt Register (that stays the authoritative, dataset-sourced
source for Loans & Finance/P1.4). For a brand-new farm with no dataset
loans, onboarding instead rolls the farmer's estimated monthly
repayment(s) into one annual "Loan Repayments" category budget, so the
cash impact is visible in Budget vs Actual immediately - a deliberate,
disclosed MVP simplification rather than a second debt-register model.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from models.financial_record import is_valid_category

FARM_TYPES = ("dairy", "beef", "suckler", "sheep", "tillage", "mixed", "other")
FARM_TYPE_LABELS: dict[str, str] = {
    "dairy": "Dairy",
    "beef": "Beef",
    "suckler": "Suckler",
    "sheep": "Sheep",
    "tillage": "Tillage",
    "mixed": "Mixed",
    "other": "Other",
}


class OnboardingBudgetItem(BaseModel):
    """One "main income" or "main cost" line - becomes one annual category budget."""

    category: str
    annual_amount: float = Field(..., ge=0)


class OnboardingLoanItem(BaseModel):
    """One loan/repayment estimate. Kept for the farmer's own record; its
    cash effect is combined into the "Loan Repayments" cost budget."""

    lender: Optional[str] = Field(default=None, max_length=120)
    monthly_repayment: float = Field(..., ge=0)
    outstanding_balance: Optional[float] = Field(default=None, ge=0)


class OnboardingRequest(BaseModel):
    farm_type: Literal["dairy", "beef", "suckler", "sheep", "tillage", "mixed", "other"]
    income_items: list[OnboardingBudgetItem] = Field(default_factory=list)
    cost_items: list[OnboardingBudgetItem] = Field(default_factory=list)
    loan_items: list[OnboardingLoanItem] = Field(default_factory=list)
    current_cash: Optional[float] = Field(default=None, description="Farmer-declared cash on hand today")
    year: Optional[int] = Field(default=None, ge=2000, le=2100, description="Defaults to the current year")

    @field_validator("income_items")
    @classmethod
    def _income_categories_known(cls, items: list[OnboardingBudgetItem]) -> list[OnboardingBudgetItem]:
        for item in items:
            if not is_valid_category("income", item.category):
                raise ValueError(f"Unknown income category '{item.category}'.")
        return items

    @field_validator("cost_items")
    @classmethod
    def _cost_categories_known(cls, items: list[OnboardingBudgetItem]) -> list[OnboardingBudgetItem]:
        for item in items:
            if not is_valid_category("expense", item.category):
                raise ValueError(f"Unknown expense category '{item.category}'.")
        return items


class OnboardingSummary(BaseModel):
    farm_type: str
    farm_type_label: str
    selected_sectors: list[str] = Field(default_factory=list)
    year: int
    income_budgets_set: int = 0
    cost_budgets_set: int = 0
    loan_repayments_annual: float = 0
    total_annual_income_budgeted: float = 0
    total_annual_cost_budgeted: float = 0
    naive_annual_net: float = 0
    current_cash_set: bool = False
    current_cash: Optional[float] = None


class OnboardingResponse(BaseModel):
    success: bool = True
    summary: OnboardingSummary


class OnboardingStatusResponse(BaseModel):
    success: bool = True
    completed: bool = False
    completed_at: Optional[str] = None
    farm_type: Optional[str] = None
    farm_type_label: Optional[str] = None
    current_cash: Optional[float] = None
    loan_repayments_annual: float = 0
    farm_types: list[dict] = Field(default_factory=list)
    income_category_choices: list[dict] = Field(default_factory=list)
    expense_category_choices: list[dict] = Field(default_factory=list)
