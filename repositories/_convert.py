"""Shared dict<->ORM value conversion helpers for the DB-backed repositories."""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime


def parse_date(value: str | None):
    return date_cls.fromisoformat(value) if value else None


def format_date(value) -> str | None:
    return value.isoformat() if value else None


def parse_datetime(value: str | None):
    return datetime.fromisoformat(value) if value else None


def format_datetime(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def to_float(value) -> float:
    return float(value) if value is not None else 0.0
