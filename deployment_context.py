"""Trusted deployment-level context for RD4 persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping


SITE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,31}$")


@dataclass(frozen=True)
class DeploymentContext:
    site_id: str
    site_name: str
    project_id: str


def resolve_deployment_context(environ: Mapping[str, str]) -> DeploymentContext:
    """Require a valid server-side facility identity before any save."""
    site_id = str(environ.get("SITE_ID", "")).strip().upper()
    site_name = str(environ.get("SITE_NAME", "")).strip()
    project_id = str(environ.get("PROJECT_ID", "")).strip()
    if not SITE_ID_PATTERN.fullmatch(site_id):
        raise RuntimeError("SITE_ID must be a valid deployment-level facility ID")
    if not site_name:
        raise RuntimeError("SITE_NAME must be configured for this deployment")
    if not project_id:
        raise RuntimeError("PROJECT_ID must be configured for this deployment")
    return DeploymentContext(
        site_id=site_id,
        site_name=site_name,
        project_id=project_id,
    )


def prepare_master_record(
    submitted_record: Mapping[str, Any],
    context: DeploymentContext,
) -> dict[str, Any]:
    """Overwrite client-controlled attribution immediately before DB save."""
    record = dict(submitted_record)
    record["facility_id"] = context.site_id
    record["site_id"] = context.site_id
    record["project_id"] = context.project_id
    return record


def anonymous_patient_code(record: Mapping[str, Any]) -> str:
    return str(
        record.get("anonymous_id")
        or record.get("visit_code")
        or record.get("patient_id")
        or ""
    ).strip().upper()


def log_save_result(
    record: Mapping[str, Any],
    context: DeploymentContext | None,
    *,
    save_result: str,
) -> None:
    """Emit a compact, answer-free persistence audit event."""
    print(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "anonymous_patient_code": anonymous_patient_code(record),
                "site_id": context.site_id if context else None,
                "project_id": context.project_id if context else None,
                "record_type": str(
                    record.get("instrument")
                    or record.get("scale")
                    or "RD4"
                ).upper(),
                "save_result": save_result,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
