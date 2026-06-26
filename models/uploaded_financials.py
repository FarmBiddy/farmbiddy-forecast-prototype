"""Pydantic models for uploaded farm financial files."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadedFinancialField(BaseModel):
    value: float
    source_column: str
    source_row: int
    source_sheet: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    original_label: str
    original_detected_field: str | None = None
    user_corrected_as: str | None = None


class UploadedFinancialData(BaseModel):
    filename: str
    detected_fields: dict[str, UploadedFinancialField] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    ready_for_forecast: bool = False


class UploadResponse(BaseModel):
    success: bool
    filename: str
    detected_fields: dict[str, UploadedFinancialField]
    warnings: list[str]
    ready_for_forecast: bool
