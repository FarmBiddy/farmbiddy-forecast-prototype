"""
Central path configuration for local and cloud deployment.

Set STORAGE_PATH in production to a persistent disk mount (e.g. on Render)
so forecast history and charts survive restarts.
"""

import os

# Project root — one level above config/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Read-only farm datasets (committed to Git)
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
FARM_PROFILE_PATH = os.path.join(BASE_DIR, "config", "farm_profile.json")

# Writable storage — defaults to outputs/ when STORAGE_PATH is unset or empty
_storage_env = os.environ.get("STORAGE_PATH", "").strip()
STORAGE_ROOT = (
    _storage_env if _storage_env else os.path.join(BASE_DIR, "outputs")
)

HISTORY_DIR = os.path.join(STORAGE_ROOT, "history")
CHARTS_DIR = os.path.join(STORAGE_ROOT, "charts")
COMPARISONS_DIR = os.path.join(STORAGE_ROOT, "comparisons")
SANDBOX_DIR = os.path.join(STORAGE_ROOT, "sandbox")
REPORTS_DIR = os.path.join(STORAGE_ROOT, "reports")
UPLOADS_DIR = os.path.join(STORAGE_ROOT, "uploads")
RAW_UPLOADS_DIR = os.path.join(UPLOADS_DIR, "raw")
PENDING_UPLOADS_DIR = os.path.join(UPLOADS_DIR, "pending")
FARM_EVENTS_DIR = os.path.join(STORAGE_ROOT, "farm_events")
DAILY_UPDATES_PATH = os.path.join(STORAGE_ROOT, "daily_updates.json")
INGESTION_REPORT_PATH = os.path.join(HISTORY_DIR, "ingestion_report.json")

# Frontend assets (committed to Git, served by FastAPI)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


def ensure_output_dirs():
    """Create writable output folders if they do not exist."""
    for folder in (
        HISTORY_DIR,
        CHARTS_DIR,
        COMPARISONS_DIR,
        SANDBOX_DIR,
        REPORTS_DIR,
        UPLOADS_DIR,
        RAW_UPLOADS_DIR,
        PENDING_UPLOADS_DIR,
        FARM_EVENTS_DIR,
    ):
        os.makedirs(folder, exist_ok=True)
