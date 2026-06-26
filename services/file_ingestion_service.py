"""
File ingestion service — reads uploaded CSV/Excel files and detects financial fields.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config.paths import INGESTION_REPORT_PATH
from models.uploaded_financials import UploadedFinancialData, UploadedFinancialField

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json"}

FIELD_KEYWORDS: dict[str, list[str]] = {
    "milk_revenue": [
        "milk revenue", "milk sales", "milk income", "dairy sales",
        "sales milk", "revenue milk",
    ],
    "milk_litres": [
        "milk litres", "milk liters", "litres", "liters", "milk volume",
        "milk production", "production litres", "total litres",
    ],
    "feed_cost": [
        "feed cost", "feed costs", "feeding cost", "concentrate cost",
        "fodder cost", "feed expense",
    ],
    "vet_cost": [
        "vet cost", "vet costs", "veterinary", "veterinary cost",
        "animal health", "vet expense",
    ],
    "labour_cost": [
        "labour cost", "labor cost", "labour costs", "labor costs",
        "wages", "staff cost", "payroll",
    ],
    "loan_repayment": [
        "loan repayment", "loan repayments", "debt repayment",
        "bank repayment", "mortgage repayment", "loan payment",
    ],
    "grant_income": [
        "grant income", "grant", "scheme payment", "subsidy", "government grant",
    ],
    "other_income": [
        "other income", "misc income", "additional income",
        "non milk income", "other revenue",
    ],
    "cash_balance": [
        "cash balance", "bank balance", "closing cash",
        "cash on hand", "current account",
    ],
    "total_costs": [
        "total costs", "total cost", "total expenses",
        "overall costs", "operating costs total",
    ],
    "profit": [
        "profit", "net profit", "monthly profit",
        "operating profit", "surplus",
    ],
}

MIN_CONFIDENCE = 0.55
LOW_CONFIDENCE_THRESHOLD = 0.70
REQUIRED_FIELDS = ("milk_revenue", "feed_cost", "cash_balance")


def normalise_label(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    cleaned = str(text).strip().lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _score_label_match(label: str, keywords: list[str]) -> tuple[float, str]:
    if not label:
        return 0.0, ""
    best_score = 0.0
    best_keyword = ""
    for keyword in keywords:
        if label == keyword:
            score = 1.0
        elif keyword in label:
            score = 0.92
        else:
            keyword_words = keyword.split()
            matched_words = sum(1 for word in keyword_words if word in label)
            if matched_words == 0:
                continue
            score = 0.65 + (0.25 * matched_words / len(keyword_words))
        if score > best_score:
            best_score = score
            best_keyword = keyword
    return best_score, best_keyword


def _parse_numeric(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("€", "").replace("$", "").replace("£", "")
    text = text.replace(",", "").replace(" ", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return float(text)
    except ValueError:
        return None


def _pick_best_numeric(values: list[Any]) -> float | None:
    numeric_values = [_parse_numeric(value) for value in values]
    numeric_values = [value for value in numeric_values if value is not None]
    if not numeric_values:
        return None
    return numeric_values[-1]


def _match_field(label: str) -> tuple[str | None, float, str]:
    best_field: str | None = None
    best_score = 0.0
    best_keyword = ""
    for field_name, keywords in FIELD_KEYWORDS.items():
        score, keyword = _score_label_match(label, keywords)
        if score > best_score:
            best_score = score
            best_field = field_name
            best_keyword = keyword
    if best_score < MIN_CONFIDENCE:
        return None, 0.0, ""
    return best_field, best_score, best_keyword


def _detect_from_row_labels(
    df: pd.DataFrame,
    sheet_name: str | None,
) -> dict[str, UploadedFinancialField]:
    detections: dict[str, UploadedFinancialField] = {}
    if df.empty or df.shape[1] < 2:
        return detections
    label_column = df.columns[0]
    for row_index, row in df.iterrows():
        label = normalise_label(row.iloc[0])
        if not label:
            continue
        field_name, confidence, _matched = _match_field(label)
        if field_name is None:
            continue
        value = _pick_best_numeric(row.iloc[1:].tolist())
        if value is None:
            continue
        source_row = int(row_index) + 2 if isinstance(row_index, int) else 2
        candidate = UploadedFinancialField(
            value=value,
            source_column=str(label_column),
            source_row=source_row,
            source_sheet=sheet_name,
            confidence=round(confidence, 2),
            original_label=str(row.iloc[0]).strip(),
            original_detected_field=field_name,
        )
        existing = detections.get(field_name)
        if existing is None or candidate.confidence > existing.confidence:
            detections[field_name] = candidate
    return detections


def _detect_from_column_headers(
    df: pd.DataFrame,
    sheet_name: str | None,
) -> dict[str, UploadedFinancialField]:
    detections: dict[str, UploadedFinancialField] = {}
    for column in df.columns:
        label = normalise_label(column)
        if not label:
            continue
        field_name, confidence, _matched = _match_field(label)
        if field_name is None:
            continue
        column_values = df[column].tolist()
        value = _pick_best_numeric(column_values)
        if value is None:
            continue
        source_row = 2
        for row_index, cell in enumerate(column_values, start=2):
            parsed = _parse_numeric(cell)
            if parsed is not None and parsed == value:
                source_row = row_index
                break
        candidate = UploadedFinancialField(
            value=value,
            source_column=str(column),
            source_row=source_row,
            source_sheet=sheet_name,
            confidence=round(confidence, 2),
            original_label=str(column).strip(),
            original_detected_field=field_name,
        )
        existing = detections.get(field_name)
        if existing is None or candidate.confidence > existing.confidence:
            detections[field_name] = candidate
    return detections


def _merge_detections(
    primary: dict[str, UploadedFinancialField],
    secondary: dict[str, UploadedFinancialField],
) -> dict[str, UploadedFinancialField]:
    merged = dict(primary)
    for field_name, candidate in secondary.items():
        existing = merged.get(field_name)
        if existing is None or candidate.confidence > existing.confidence:
            merged[field_name] = candidate
    return merged


def _detect_in_dataframe(
    df: pd.DataFrame,
    sheet_name: str | None = None,
) -> dict[str, UploadedFinancialField]:
    cleaned = df.dropna(how="all").dropna(axis=1, how="all")
    if cleaned.empty:
        return {}
    row_hits = _detect_from_row_labels(cleaned, sheet_name)
    column_hits = _detect_from_column_headers(cleaned, sheet_name)
    return _merge_detections(row_hits, column_hits)


def _read_file(path: Path) -> dict[str | None, pd.DataFrame]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return {None: pd.read_csv(path)}
    if suffix == ".xlsx":
        return pd.read_excel(path, sheet_name=None, engine="openpyxl")
    if suffix == ".json":
        return _read_json_financials(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _read_json_financials(path: Path) -> dict[str | None, pd.DataFrame]:
    """Parse JSON farm/financial files into a detectable DataFrame."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, (int, float)) and not key.startswith("_"):
                rows.append({"label": key.replace("_", " "), "value": value})
        if "monthly_forecast" in raw and isinstance(raw["monthly_forecast"], list):
            for item in raw["monthly_forecast"]:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if isinstance(v, (int, float)):
                            rows.append({"label": f"monthly {k}", "value": v})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                label = item.get("label") or item.get("name") or item.get("field", "")
                value = item.get("value") or item.get("amount")
                if label and value is not None:
                    rows.append({"label": str(label), "value": value})
    if not rows:
        raise ValueError("JSON file contains no detectable financial numbers.")
    return {None: pd.DataFrame(rows)}


def _validate_detections(
    detected_fields: dict[str, UploadedFinancialField],
) -> tuple[list[str], bool]:
    warnings: list[str] = []
    if not detected_fields:
        warnings.append("No financial fields were detected in the uploaded file.")
    missing_required = [
        field_name for field_name in REQUIRED_FIELDS if field_name not in detected_fields
    ]
    if missing_required:
        warnings.append("Missing required fields: " + ", ".join(missing_required))
    low_confidence = [
        field_name
        for field_name, field in detected_fields.items()
        if field.confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    if low_confidence:
        warnings.append(
            "Low-confidence detections (below 0.70): " + ", ".join(sorted(low_confidence))
        )
    ready_for_forecast = len(missing_required) == 0
    return warnings, ready_for_forecast


def save_ingestion_report(
    detected_data: UploadedFinancialData,
    output_path: Path | None = None,
) -> Path:
    report_path = output_path or INGESTION_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "filename": detected_data.filename,
        "detected_fields": {
            name: field.model_dump() for name, field in detected_data.detected_fields.items()
        },
        "warnings": detected_data.warnings,
        "ready_for_forecast": detected_data.ready_for_forecast,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


class FileIngestionService:
    """Parse uploaded farm financial files and return structured detections."""

    def ingest_file(self, file_path: Path, filename: str | None = None) -> UploadedFinancialData:
        resolved_name = filename or file_path.name
        suffix = file_path.suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{suffix}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        detected_fields: dict[str, UploadedFinancialField] = {}
        sheets = _read_file(file_path)
        for sheet_name, dataframe in sheets.items():
            sheet_hits = _detect_in_dataframe(dataframe, sheet_name)
            detected_fields = _merge_detections(detected_fields, sheet_hits)
        warnings, ready_for_forecast = _validate_detections(detected_fields)
        return UploadedFinancialData(
            filename=resolved_name,
            detected_fields=detected_fields,
            warnings=warnings,
            ready_for_forecast=ready_for_forecast,
        )
