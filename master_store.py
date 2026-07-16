from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Mapping
import json
import os
import re
import uuid

JST = timezone(timedelta(hours=9))
COLUMNS = (
    "submission_id", "facility_id", "project_id", "schema_version", "anonymous_id",
    "disease", "scale", "submitted_at", "total_score", "max_score", "severity",
    "previous_score", "delta_score", "decision", "input_duration_seconds",
    "input_support", "input_ease", "consent_checked", "source_app", "source_version",
    "visit_type", "treatment_context", "responder_role", "responses_json", "extra_json",
)
KNOWN = {
    "submission_id", "facility_id", "site_id", "project_id", "anonymous_id", "visit_code",
    "patient_id", "disease", "scale", "instrument", "submitted_at", "timestamp",
    "input_submitted_at", "total_score", "max_score", "severity", "previous_score",
    "previous_adct", "delta_score", "delta_adct", "decision", "input_duration_seconds",
    "input_support", "input_ease", "consent_checked", "research_consent_checked",
    "source_app", "source_version", "app_version", "visit_type", "treatment_context",
    "responder_role", "responses_json", "extra_json",
}


def _pick(row: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return default


def _int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "checked", "同意"}


def _id(value: Any) -> str:
    return "".join(str(value or "").strip().upper().split())


def _timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(JST).isoformat(timespec="seconds")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.isoformat(timespec="seconds")


def _responses(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in row:
        match = re.fullmatch(r"q(\d+)_score", str(key))
        if match:
            number = match.group(1)
            result[f"q{number}"] = {
                "score": _int(row.get(key)),
                "answer": str(row.get(f"q{number}_answer", "") or ""),
            }
    return result


def canonical_row(row: Mapping[str, Any], *, facility_id: str, project_id: str) -> dict[str, Any]:
    scale = str(_pick(row, "scale", "instrument")).strip().upper()
    anonymous_id = _id(_pick(row, "anonymous_id", "visit_code", "patient_id"))
    submitted_at = _timestamp(_pick(row, "submitted_at", "timestamp", "input_submitted_at"))
    total_score = _int(_pick(row, "total_score", "total"))
    max_score = _int(row.get("max_score")) or {"ADCT": 24, "UCT": 16, "DLQI": 30}.get(scale)
    actual_facility = str(_pick(row, "facility_id", "site_id", default=facility_id)).strip()
    actual_project = str(_pick(row, "project_id", default=project_id)).strip()
    fingerprint = "|".join([actual_facility, anonymous_id, scale, submitted_at, str(total_score), actual_project])
    extra = {
        str(key): value for key, value in row.items()
        if str(key) not in KNOWN
        and not re.fullmatch(r"q\d+_(score|answer)", str(key))
        and value is not None and str(value).strip() != ""
    }
    return {
        "submission_id": str(row.get("submission_id") or uuid.uuid5(uuid.NAMESPACE_URL, fingerprint)),
        "facility_id": actual_facility,
        "project_id": actual_project,
        "schema_version": 1,
        "anonymous_id": anonymous_id,
        "disease": str(row.get("disease", "") or "").strip(),
        "scale": scale,
        "submitted_at": submitted_at,
        "total_score": total_score,
        "max_score": max_score,
        "severity": str(row.get("severity", "") or "").strip(),
        "previous_score": _int(_pick(row, "previous_score", "previous_adct")),
        "delta_score": _int(_pick(row, "delta_score", "delta_adct")),
        "decision": str(row.get("decision", "") or "").strip(),
        "input_duration_seconds": _float(row.get("input_duration_seconds")),
        "input_support": str(row.get("input_support", "") or "").strip(),
        "input_ease": str(row.get("input_ease", "") or "").strip(),
        "consent_checked": _bool(_pick(row, "consent_checked", "research_consent_checked")),
        "source_app": str(row.get("source_app", "RD4") or "RD4").strip(),
        "source_version": str(_pick(row, "source_version", "app_version")).strip(),
        "visit_type": str(row.get("visit_type", "") or "").strip(),
        "treatment_context": str(row.get("treatment_context", "") or "").strip(),
        "responder_role": str(row.get("responder_role", "") or "").strip(),
        "responses_json": _responses(row),
        "extra_json": extra,
    }


class ProStore:
    def __init__(self, database_url: str | None = None) -> None:
        raw = (database_url or os.getenv("DATABASE_URL", "")).strip()
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://"):]
        if not raw:
            raise RuntimeError("DATABASE_URL is not configured")
        self.database_url = raw
        self.ensure_schema()

    def _connect(self):
        import psycopg
        return psycopg.connect(self.database_url)

    def ensure_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS pro_submissions (
                submission_id TEXT PRIMARY KEY,
                facility_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                anonymous_id TEXT NOT NULL,
                disease TEXT NOT NULL DEFAULT '',
                scale TEXT NOT NULL,
                submitted_at TIMESTAMPTZ NOT NULL,
                total_score INTEGER,
                max_score INTEGER,
                severity TEXT NOT NULL DEFAULT '',
                previous_score INTEGER,
                delta_score INTEGER,
                decision TEXT NOT NULL DEFAULT '',
                input_duration_seconds DOUBLE PRECISION,
                input_support TEXT NOT NULL DEFAULT '',
                input_ease TEXT NOT NULL DEFAULT '',
                consent_checked BOOLEAN NOT NULL DEFAULT FALSE,
                source_app TEXT NOT NULL DEFAULT '',
                source_version TEXT NOT NULL DEFAULT '',
                visit_type TEXT NOT NULL DEFAULT '',
                treatment_context TEXT NOT NULL DEFAULT '',
                responder_role TEXT NOT NULL DEFAULT '',
                responses_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_pro_patient ON pro_submissions (facility_id, anonymous_id, scale, submitted_at)",
            "CREATE INDEX IF NOT EXISTS idx_pro_time ON pro_submissions (facility_id, submitted_at DESC)",
        )
        with self._connect() as conn:
            for statement in statements:
                conn.execute(statement)

    def save_row(self, row: Mapping[str, Any], *, facility_id: str, project_id: str) -> bool:
        from psycopg.types.json import Jsonb
        canonical = canonical_row(row, facility_id=facility_id, project_id=project_id)
        if not canonical["anonymous_id"] or not canonical["scale"]:
            raise ValueError("anonymous_id and scale are required")
        values = [canonical[column] for column in COLUMNS]
        values[COLUMNS.index("responses_json")] = Jsonb(canonical["responses_json"])
        values[COLUMNS.index("extra_json")] = Jsonb(canonical["extra_json"])
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        sql = f"INSERT INTO pro_submissions ({', '.join(COLUMNS)}) VALUES ({placeholders}) ON CONFLICT (submission_id) DO NOTHING"
        with self._connect() as conn:
            cursor = conn.execute(sql, values)
            return cursor.rowcount == 1
