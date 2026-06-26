"""Daily farm updates — record today's income and costs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config.paths import DAILY_UPDATES_PATH
from models.farm_update import DailyUpdateEntry, DailyUpdateRequest, DailyUpdateResponse, ProfileFieldChange
from models.farmer_categories import DAILY_CATEGORY_TO_PROFILE_FIELD, DAILY_UPDATE_CATEGORIES
from services.fi_farm_profile_service import load_farm_dataset, save_farm_dataset


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_ledger() -> list[dict[str, Any]]:
    if not DAILY_UPDATES_PATH or not __import__("os").path.exists(DAILY_UPDATES_PATH):
        return []
    try:
        data = json.loads(open(DAILY_UPDATES_PATH, encoding="utf-8").read())
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _save_ledger(entries: list[dict[str, Any]]) -> None:
    import os
    os.makedirs(os.path.dirname(DAILY_UPDATES_PATH), exist_ok=True)
    with open(DAILY_UPDATES_PATH, "w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)


def list_daily_update_categories() -> list[dict[str, str]]:
    return [{"id": k, "label": v} for k, v in DAILY_UPDATE_CATEGORIES.items()]


def apply_daily_updates(request: DailyUpdateRequest) -> DailyUpdateResponse:
    profile = load_farm_dataset(request.farm_file)
    applied: list[DailyUpdateEntry] = []
    changes: list[ProfileFieldChange] = []
    warnings: list[str] = []

    for entry in request.entries:
        if entry.category_id not in DAILY_UPDATE_CATEGORIES:
            warnings.append(f"Unknown category: {entry.category_id}")
            continue
        if entry.amount == 0:
            continue

        field = DAILY_CATEGORY_TO_PROFILE_FIELD[entry.category_id]
        previous = profile.get(field)
        if previous is not None:
            previous = float(previous)

        if entry.category_id == "milk_income":
            new_value = (previous or float(profile.get("opening_cash_balance", 0))) + entry.amount
            profile["opening_cash_balance"] = new_value
        else:
            new_value = (previous or 0.0) + entry.amount
            profile[field] = new_value

        applied.append(entry)
        changes.append(
            ProfileFieldChange(
                profile_field=field,
                category_id=entry.category_id,
                previous_value=previous,
                new_value=new_value,
            )
        )

    if not applied:
        return DailyUpdateResponse(
            success=False,
            message="No daily updates were applied.",
            applied_entries=[],
            profile_changes=[],
            warnings=warnings or ["Enter at least one amount to save."],
        )

    profile["last_daily_update"] = _utc_now()
    save_farm_dataset(profile, request.farm_file)

    ledger = _load_ledger()
    ledger.insert(
        0,
        {
            "timestamp": _utc_now(),
            "note": request.note,
            "entries": [e.model_dump() for e in applied],
        },
    )
    _save_ledger(ledger[:100])

    return DailyUpdateResponse(
        success=True,
        message="Today's updates were saved. Your forecasts will use the new numbers.",
        applied_entries=applied,
        profile_changes=changes,
        warnings=warnings,
    )


def recent_daily_updates(limit: int = 5) -> list[dict[str, Any]]:
    return _load_ledger()[:limit]
