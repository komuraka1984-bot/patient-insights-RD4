"""Conference-only questionnaire defaults and idempotent demo history."""

from __future__ import annotations

from typing import Any


CONFERENCE_SITE_ID = "CONFERENCE_DEMO"


def is_conference_demo(site_id: object) -> bool:
    return str(site_id or "").strip().upper() == CONFERENCE_SITE_ID


def allowed_scales(site_id: object, default: tuple[str, ...]) -> tuple[str, ...]:
    return ("UCT",) if is_conference_demo(site_id) else tuple(default)


def anonymous_code_digits(site_id: object) -> str:
    return "001" if is_conference_demo(site_id) else ""


def uc001_history_rows() -> tuple[dict[str, Any], ...]:
    """Return deterministic rows so repeated deployments never duplicate them."""
    return (
        {
            "submission_id": "conference-demo-uc001-2026-02-18",
            "anonymous_id": "UC001",
            "disease": "Urticaria",
            "scale": "UCT",
            "submitted_at": "2026-02-18T09:00:00+09:00",
            "total_score": 3,
            "max_score": 16,
            "severity": "コントロール不良の可能性",
            "source_app": "RD4_DEMO_SEED",
            "q1_score": 0,
            "q2_score": 1,
            "q3_score": 1,
            "q4_score": 1,
        },
        {
            "submission_id": "conference-demo-uc001-2026-06-18",
            "anonymous_id": "UC001",
            "disease": "Urticaria",
            "scale": "UCT",
            "submitted_at": "2026-06-18T09:00:00+09:00",
            "total_score": 7,
            "max_score": 16,
            "severity": "コントロール不良の可能性",
            "previous_score": 3,
            "delta_score": 4,
            "source_app": "RD4_DEMO_SEED",
            "q1_score": 1,
            "q2_score": 2,
            "q3_score": 2,
            "q4_score": 2,
        },
    )
