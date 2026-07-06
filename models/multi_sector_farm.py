"""Constants and helpers for multi-sector farm datasets."""

from __future__ import annotations

MULTI_SECTOR_FILE = "multi_sector_farm.json"
SCHEMA_VERSION = "2.0"
VALID_SECTORS = ("dairy", "beef", "lamb")

SECTOR_LABELS = {
    "dairy": "Dairy",
    "beef": "Beef",
    "lamb": "Lamb",
}

DEFAULT_SECTORS = list(VALID_SECTORS)
