"""Map detected upload fields into farmer-friendly categories."""

from __future__ import annotations

from models.farm_update import FarmerCategoryPreview
from models.farmer_categories import (
    CATEGORY_TO_PROFILE_FIELD,
    DETECTED_FIELD_TO_CATEGORY,
    FARMER_CATEGORIES,
)
from models.uploaded_financials import UploadedFinancialData, UploadedFinancialField


def _pick_best_field_for_category(
    category_id: str,
    detected_fields: dict[str, UploadedFinancialField],
) -> tuple[str, UploadedFinancialField] | None:
    matches: list[tuple[str, UploadedFinancialField]] = []
    for field_key, field in detected_fields.items():
        if DETECTED_FIELD_TO_CATEGORY.get(field_key) == category_id:
            matches.append((field_key, field))
    if not matches:
        return None
    matches.sort(key=lambda item: item[1].confidence, reverse=True)
    return matches[0]


def build_farmer_category_previews(
    detected_data: UploadedFinancialData,
    current_profile: dict,
) -> dict[str, FarmerCategoryPreview]:
    previews: dict[str, FarmerCategoryPreview] = {}
    for category_id, label in FARMER_CATEGORIES.items():
        profile_field = CATEGORY_TO_PROFILE_FIELD[category_id]
        current_value = current_profile.get(profile_field)
        if category_id == "milk_income":
            cows = float(current_profile.get("milking_cows", 0))
            litres = float(current_profile.get("litres_per_cow", 0))
            price = float(current_profile.get("milk_price", 0))
            if cows and litres and price:
                current_value = cows * litres * price
        if current_value is not None:
            current_value = float(current_value)

        match = _pick_best_field_for_category(category_id, detected_data.detected_fields)
        if match is None:
            continue

        internal_key, field = match
        proposed_value = float(field.value)
        previews[category_id] = FarmerCategoryPreview(
            category_id=category_id,
            label=label,
            detected_value=proposed_value,
            current_profile_value=current_value,
            proposed_profile_value=proposed_value,
            profile_field=profile_field,
            confidence=field.confidence,
            original_label=field.original_label,
            source_column=field.source_column,
            source_row=field.source_row,
            source_sheet=field.source_sheet,
            selected_by_default=field.confidence >= 0.70,
            internal_field_key=internal_key,
        )
    return previews


def categories_ready_to_apply(farmer_categories: dict[str, FarmerCategoryPreview]) -> bool:
    return len(farmer_categories) > 0
