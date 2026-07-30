"""Shared, token-routed RD4 patient entry for staging and future rollout."""

from __future__ import annotations

import time

import streamlit as st

import app_master as base
import app as legacy
from deployment_context import log_save_result, prepare_master_record
from facility_access import FacilityStore


@st.cache_resource
def get_facility_store() -> FacilityStore:
    return FacilityStore(base.DATABASE_URL)


def resolve_shared_patient_context():
    # Deliberately inspect only the opaque token. A supplied facility/site
    # query parameter is never read or used to choose a tenant.
    token = str(st.query_params.get("access", "") or "").strip()
    if not token:
        st.error(
            "この患者用リンクは無効です。受付から案内された"
            "最新のQRコードをご利用ください。"
        )
        st.stop()
    try:
        context = get_facility_store().resolve_patient_access_token(token)
    except Exception as exc:
        print("SHARED PATIENT ACCESS ERROR:", repr(exc), flush=True)
        context = None
    if context is None:
        st.error(
            "この患者用リンクは無効または停止中です。"
            "受付で最新のQRコードをご確認ください。"
        )
        st.stop()
    return context


_facility_context = resolve_shared_patient_context()
legacy.SITE_ID = _facility_context.facility_id
legacy.SITE_NAME = _facility_context.facility_name
legacy.PROJECT_ID = _facility_context.project_id
legacy.PROJECT_PHASE = (
    "RESEARCH"
    if _facility_context.usage_mode == "research"
    else "FLOW"
)
legacy.RESEARCH_MODE = _facility_context.usage_mode == "research"
legacy.EXTERNAL_FACILITY_MODE = True
legacy.ALLOWED_SCALES = _facility_context.allowed_scales
legacy.FACILITY_CONTACT = "contact@shirabeo.com"


def save_result_with_shared_context(row: dict) -> None:
    """Persist only with the facility context resolved from the access token."""
    enriched = dict(row)
    instrument = str(enriched.get("instrument", "")).upper()
    enriched.update(
        {
            "source_app": "RD4",
            "source_version": enriched.get("app_version", ""),
            "visit_type": base._extra_value(instrument, "visit_type"),
            "treatment_context": base._extra_value(
                instrument,
                "treatment_context",
            ),
            "responder_role": base._extra_value(
                instrument,
                "responder_role",
            ),
        }
    )

    if base._pro_store is None:
        log_save_result(
            enriched,
            None,
            save_result="rejected_master_db_unavailable",
        )
        st.error(
            "マスターデータベースへ接続できないため送信を完了できません。"
            "時間をおいて再度お試しください。"
        )
        st.stop()

    started = time.perf_counter()
    try:
        # Final save-time overwrite. The user, browser, URL, and submitted row
        # have no path to override these values.
        enriched = prepare_master_record(enriched, _facility_context)
        inserted = base._pro_store.save_row(
            enriched,
            facility_id=_facility_context.facility_id,
            project_id=_facility_context.project_id,
        )
        print(
            f"MASTER_DB_SECONDS={time.perf_counter() - started:.3f}",
            flush=True,
        )
        log_save_result(
            enriched,
            _facility_context,
            save_result="inserted" if inserted else "duplicate",
        )
    except Exception as exc:
        print(
            f"MASTER_DB_SECONDS={time.perf_counter() - started:.3f}",
            flush=True,
        )
        print("MASTER DB SAVE ERROR:", repr(exc), flush=True)
        log_save_result(enriched, _facility_context, save_result="error")
        st.error(
            "マスターデータベースへ保存できなかったため、"
            "送信は完了していません。時間をおいて再度お試しください。"
        )
        st.stop()


legacy.save_result = save_result_with_shared_context


def get_previous_adct_from_shared_context(patient_code: str):
    if base._pro_store is None:
        return base.legacy._master_original_get_previous_adct(patient_code)
    return base._pro_store.latest_score(
        patient_code,
        facility_id=_facility_context.facility_id,
        scale="ADCT",
    )


legacy.get_previous_adct = get_previous_adct_from_shared_context


def restrict_renderer(renderer, instrument: str):
    def wrapped(language: str):
        if instrument not in set(_facility_context.allowed_scales):
            st.error("この施設では、この質問票は現在有効化されていません。")
            st.stop()
        return renderer(language)

    wrapped.__name__ = f"shared_token_{instrument.lower()}"
    return wrapped


for _renderer_name, _instrument in (
    ("render_adct", "ADCT"),
    ("render_dlqi", "DLQI"),
    ("render_uct", "UCT"),
):
    setattr(
        legacy,
        _renderer_name,
        restrict_renderer(getattr(legacy, _renderer_name), _instrument),
    )


if __name__ == "__main__":
    legacy.main()
