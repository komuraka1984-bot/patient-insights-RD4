from __future__ import annotations

from typing import Any, Mapping
import json
import os

import requests

SHEET_MIRROR_URL = os.getenv("SHEET_MIRROR_URL", "").strip()
SHEET_MIRROR_TOKEN = os.getenv("SHEET_MIRROR_TOKEN", "").strip()


def mirror_record(record_type: str, row: Mapping[str, Any]) -> tuple[bool, str]:
    if not SHEET_MIRROR_URL:
        return False, "disabled"
    payload = {
        "action": "upsert_master",
        "record_type": record_type,
        "token": SHEET_MIRROR_TOKEN,
        "data": _json_safe(dict(row)),
    }
    try:
        response = requests.post(SHEET_MIRROR_URL, json=payload, timeout=12, allow_redirects=True)
        response.raise_for_status()
        body = response.json()
        if body.get("result") != "success":
            return False, str(body.get("message", "mirror failed"))
        return True, str(body.get("message", "mirrored"))
    except (requests.RequestException, ValueError) as exc:
        print(f"SHEET MIRROR WARNING: {exc}")
        return False, str(exc)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
