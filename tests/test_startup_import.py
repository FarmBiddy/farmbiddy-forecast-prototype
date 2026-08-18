"""Startup must not import matplotlib or create schema before Uvicorn can bind."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(code: str, tmp_path) -> str:
    env = os.environ.copy()
    env["STORAGE_PATH"] = str(tmp_path)
    env["PERSISTENCE_BACKEND"] = "db"
    env["IDENTITY_PROVIDER"] = "dev"
    env["FARMBIDDY_SEED_DEMO"] = "0"
    env.pop("DATABASE_URL", None)
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_importing_api_main_does_not_load_matplotlib_pyplot(tmp_path):
    out = _run(
        "import sys, api.main\n"
        "assert 'matplotlib.pyplot' not in sys.modules\n"
        "print('ok')\n",
        tmp_path,
    )
    assert "ok" in out


def test_importing_db_session_does_not_create_schema(tmp_path):
    out = _run(
        "from sqlalchemy import inspect\n"
        "import db.session as s\n"
        "assert 'farms' not in inspect(s.engine).get_table_names()\n"
        "s.init_db()\n"
        "assert 'farms' in inspect(s.engine).get_table_names()\n"
        "print('ok')\n",
        tmp_path,
    )
    assert "ok" in out
