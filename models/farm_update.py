"""Farm profile update models for upload preview and confirmation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from models.uploaded_financials import UploadedFinancialField


class FarmerCategoryPreview(BaseModel):
    category_id: str
    label: str
    detected_value: float | None = None
    current_profile_value: float | None = None
    proposed_profile_value: float | None = None
    profile_field: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    original_label: str | None = None
    source_column: str | None = None
    source_row: int | None = None
    source_sheet: str | None = None
    selected_by_default: bool = True
    internal_field_key: str | None = None


class FarmUpdatePreviewResponse(BaseModel):
    success: bool = True
    message: str = "Review detected values before updating your farm."
    upload_id: str
    filename: str
    farm_name: str
    farmer_categories: dict[str, FarmerCategoryPreview]
    detected_fields: dict[str, UploadedFinancialField] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    ready_to_apply: bool = False


class ApplyFarmUpdateRequest(BaseModel):
    upload_id: str
    filename: str
    farm_name: str | None = None
    selected_categories: list[str]
    detected_fields: dict[str, UploadedFinancialField]
    farmer_categories: dict[str, FarmerCategoryPreview]


class ProfileFieldChange(BaseModel):
    profile_field: str
    category_id: str
    previous_value: float | None = None
    new_value: float


class ApplyFarmUpdateResponse(BaseModel):
    success: bool
    message: str
    farm_name: str
    applied_categories: list[str]
    skipped_categories: list[str] = Field(default_factory=list)
    profile_changes: list[ProfileFieldChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DailyUpdateEntry(BaseModel):
    category_id: str
    amount: float
    note: str = ""
    date: str | None = None


class DailyUpdateRequest(BaseModel):
    entries: list[DailyUpdateEntry]
    note: str = ""


class DailyUpdateResponse(BaseModel):
    success: bool
    message: str
    applied_entries: list[DailyUpdateEntry] = Field(default_factory=list)
    profile_changes: list[ProfileFieldChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FarmSettingsUpdate(BaseModel):
    farm_name: str | None = None
    milking_cows: int | None = None
    milk_processor: str | None = None
    milk_price: float | None = None
    opening_cash_balance: float | None = None
    litres_per_cow: float | None = None
    interest_rate: float | None = None
    inflation: float | None = None
    currency: str | None = None
    country: str | None = None
    owner_name: str | None = None
    location: str | None = None


class FarmSettingsResponse(BaseModel):
    success: bool
    message: str
    farm_profile: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
