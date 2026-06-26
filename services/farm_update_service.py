"""Upload preview and confirmed farm profile updates."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import FARM_EVENTS_DIR, FARM_PROFILE_PATH, PENDING_UPLOADS_DIR
from models.farm_update import (
    ApplyFarmUpdateRequest,
    ApplyFarmUpdateResponse,
    FarmUpdatePreviewResponse,
    ProfileFieldChange,
)
from models.uploaded_financials import UploadedFinancialData
from services.farmer_category_service import (
    build_farmer_category_previews,
    categories_ready_to_apply,
)
from services.fi_farm_profile_service import (
    load_farm_dataset,
    load_farm_profile_config,
    save_farm_dataset,
)
from services.forecast_service import InvalidFarmDataError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_pending_upload(upload_id: str, payload: dict[str, Any]) -> None:
    Path(PENDING_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(PENDING_UPLOADS_DIR) / f"{upload_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _apply_category_value(profile: dict, category_id: str, preview) -> tuple[str, float, float | None]:
    """Apply a farmer category to the DAIRY farm JSON schema."""
    proposed = float(preview.proposed_profile_value)
    field = preview.profile_field
    previous = profile.get(field)
    if previous is not None:
        previous = float(previous)

    if category_id == "milk_income":
        cows = float(profile.get("milking_cows", 120))
        litres = float(profile.get("litres_per_cow", 5500))
        denom = cows * litres
        if denom <= 0:
            raise ValueError("Cannot derive milk price — milking cows or litres per cow missing.")
        previous = float(profile.get("milk_price", 0))
        new_value = round(proposed / denom, 4)
        profile["milk_price"] = new_value
        return "milk_price", previous, new_value

    new_value = proposed
    profile[field] = new_value
    return field, previous, new_value


def build_upload_preview(
    upload_id: str,
    ingested: UploadedFinancialData,
    farm_file: str | None = None,
) -> FarmUpdatePreviewResponse:
    profile = load_farm_dataset(farm_file)
    config = load_farm_profile_config()
    farmer_categories = build_farmer_category_previews(ingested, profile)
    preview = FarmUpdatePreviewResponse(
        upload_id=upload_id,
        filename=ingested.filename,
        farm_name=config.get("farm_display_name") or profile.get("farm_name", "My Farm"),
        farmer_categories=farmer_categories,
        detected_fields=ingested.detected_fields,
        warnings=ingested.warnings,
        ready_to_apply=categories_ready_to_apply(farmer_categories),
    )
    _save_pending_upload(
        upload_id,
        {
            "upload_id": upload_id,
            "filename": ingested.filename,
            "detected_fields": {k: v.model_dump() for k, v in ingested.detected_fields.items()},
            "farmer_categories": {k: v.model_dump() for k, v in farmer_categories.items()},
            "warnings": ingested.warnings,
            "created_at": _utc_now(),
        },
    )
    return preview


def apply_farm_update(request: ApplyFarmUpdateRequest) -> ApplyFarmUpdateResponse:
    profile = load_farm_dataset(request.farm_file)
    config = load_farm_profile_config()
    applied: list[str] = []
    skipped: list[str] = []
    changes: list[ProfileFieldChange] = []
    warnings: list[str] = []

    if request.farm_name:
        profile["farm_name"] = request.farm_name
        config["farm_display_name"] = request.farm_name

    selected = set(request.selected_categories)
    for category_id, preview in request.farmer_categories.items():
        if category_id not in selected:
            skipped.append(category_id)
            continue
        if preview.proposed_profile_value is None:
            warnings.append(f"No value to apply for {preview.label}.")
            skipped.append(category_id)
            continue
        try:
            field, previous, new_value = _apply_category_value(profile, category_id, preview)
        except ValueError as error:
            warnings.append(str(error))
            skipped.append(category_id)
            continue
        changes.append(
            ProfileFieldChange(
                profile_field=field,
                category_id=category_id,
                previous_value=previous,
                new_value=new_value,
            )
        )
        applied.append(category_id)

    if not applied:
        return ApplyFarmUpdateResponse(
            success=False,
            message="No categories were applied. Your farm profile was not changed.",
            farm_name=str(profile.get("farm_name", "My Farm")),
            applied_categories=applied,
            skipped_categories=skipped,
            profile_changes=changes,
            warnings=warnings or ["Select at least one category before confirming."],
        )

    profile["last_updated"] = _utc_now()
    profile["last_upload_filename"] = request.filename
    save_farm_dataset(profile, request.farm_file)
    with open(FARM_PROFILE_PATH, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)

    Path(FARM_EVENTS_DIR).mkdir(parents=True, exist_ok=True)
    event_path = Path(FARM_EVENTS_DIR) / f"{_utc_now().replace(':', '-')}_{request.upload_id}.json"
    event_path.write_text(
        json.dumps(
            {
                "event_id": request.upload_id,
                "timestamp": _utc_now(),
                "source_filename": request.filename,
                "applied_categories": applied,
                "profile_changes": [c.model_dump() for c in changes],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return ApplyFarmUpdateResponse(
        success=True,
        message="Your farm profile was updated with the selected numbers.",
        farm_name=str(profile.get("farm_name", "My Farm")),
        applied_categories=applied,
        skipped_categories=skipped,
        profile_changes=changes,
        warnings=warnings,
    )


def get_latest_upload_info() -> dict[str, Any]:
    profile = load_farm_dataset()
    events_dir = Path(FARM_EVENTS_DIR)
    if not events_dir.exists():
        return {
            "filename": profile.get("last_upload_filename"),
            "last_updated": profile.get("last_updated"),
        }
    events = sorted(events_dir.glob("*.json"), reverse=True)
    if not events:
        return {
            "filename": profile.get("last_upload_filename"),
            "last_updated": profile.get("last_updated"),
        }
    latest = json.loads(events[0].read_text(encoding="utf-8"))
    return {
        "filename": latest.get("source_filename"),
        "last_updated": latest.get("timestamp"),
        "applied_categories": latest.get("applied_categories", []),
    }
