"""Active farm dataset helpers for upload and daily updates (Farmer Edition)."""

from __future__ import annotations

import json
import os
from typing import Any

from config.paths import DATASETS_DIR, FARM_PROFILE_PATH
from services.farmer_dashboard_service import get_active_farm_file
from services.forecast_service import InvalidFarmDataError, load_farm, save_farm


def load_farm_profile_config() -> dict[str, Any]:
    if not os.path.exists(FARM_PROFILE_PATH):
        return {
            "edition": "farmer",
            "active_farm_file": "dairy_farm_1.json",
            "farm_display_name": "My Farm",
        }
    with open(FARM_PROFILE_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise InvalidFarmDataError("Farm profile config must be a JSON object.")
    return data


def load_farm_dataset(farm_file: str | None = None) -> dict[str, Any]:
    """Load the active or specified farm JSON dataset."""
    farm_file = farm_file or get_active_farm_file()
    return load_farm(farm_file)


def save_farm_dataset(profile: dict[str, Any], farm_file: str | None = None) -> str:
    """Persist changes to the active or specified farm dataset."""
    farm_file = farm_file or get_active_farm_file()
    save_farm(farm_file, profile)
    return farm_file


def get_active_farm_file_name() -> str:
    return get_active_farm_file()
