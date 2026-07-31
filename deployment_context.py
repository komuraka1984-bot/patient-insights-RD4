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


@dataclass(frozen=True)
class RequestContext:
    """Server-resolved tenant settings for one patient browser session."""

    deployment: DeploymentContext
    allowed_scales: tuple[str, ...]
    external: bool
    research_mode: bool


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


def resolve_request_context(
    default_context: DeploymentContext,
    *,
    facility_store: Any,
    access_token: object = "",
    requested_facility_id: object = "",
    default_allowed_scales: tuple[str, ...] = ("ADCT", "DLQI", "UCT"),
    default_research_mode: bool = True,
) -> RequestContext:
    """
    Resolve an external tenant only from a valid opaque patient token.

    The optional facility query parameter is a consistency check, never the
    source of tenant identity. A supplied but invalid token fails closed rather
    than falling back to the default deployment.
    """
    token = str(access_token or "").strip()
    if not token:
        requested_id = str(requested_facility_id or "").strip().upper()
        if requested_id and requested_id != default_context.site_id:
            raise RuntimeError(
                "external facility access requires a valid patient token"
            )
        return RequestContext(
            deployment=default_context,
            allowed_scales=tuple(default_allowed_scales),
            external=False,
            research_mode=bool(default_research_mode),
        )

    if facility_store is None:
        raise RuntimeError(
            "patient access cannot be validated without the facility store"
        )

    facility = facility_store.resolve_patient_access_token(token)
    if facility is None:
        raise RuntimeError("patient access token is invalid or disabled")

    resolved_id = str(facility.facility_id or "").strip().upper()
    requested_id = str(requested_facility_id or "").strip().upper()
    if requested_id and requested_id != resolved_id:
        raise RuntimeError(
            "patient access token does not match the requested facility"
        )

    deployment = DeploymentContext(
        site_id=resolved_id,
        site_name=str(facility.facility_name or "").strip(),
        project_id=str(facility.project_id or "").strip(),
    )
    if not SITE_ID_PATTERN.fullmatch(deployment.site_id):
        raise RuntimeError("resolved facility ID is invalid")
    if not deployment.site_name or not deployment.project_id:
        raise RuntimeError("resolved facility configuration is incomplete")

    return RequestContext(
        deployment=deployment,
        allowed_scales=tuple(facility.allowed_scales),
        external=True,
        research_mode=str(facility.usage_mode or "").strip() == "research",
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
