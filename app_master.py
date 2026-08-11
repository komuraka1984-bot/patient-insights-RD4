from __future__ import annotations

import os
import time

import streamlit as st

import app as legacy
from deployment_context import (
    DeploymentContext,
    RequestContext,
    log_save_result,
    prepare_master_record,
    resolve_deployment_context,
    resolve_request_context,
)
from facility_access import FacilityStore
from master_store import ProStore


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MASTER_REQUIRED = (
    os.getenv("MASTER_DB_REQUIRED", "true").strip().lower()
    not in {"0", "false", "no"}
)
ALLOW_EXTERNAL_FACILITY_ACCESS = (
    os.getenv("ALLOW_EXTERNAL_FACILITY_ACCESS", "true").strip().lower()
    not in {"0", "false", "no", "off"}
)

_pro_store: ProStore | None = ProStore(DATABASE_URL) if DATABASE_URL else None
_facility_store: FacilityStore | None = (
    FacilityStore(DATABASE_URL) if DATABASE_URL else None
)

try:
    _deployment_context: DeploymentContext = resolve_deployment_context(
        os.environ
    )
except RuntimeError as exc:
    # Fail closed: no persistence and no completion screen without a valid
    # server-side facility identity.
    st.error(
        "この施設の保存設定が不完全なため送信できません。"
        "管理者へご連絡ください。"
    )
    print(f"RD4 DEPLOYMENT CONFIG ERROR: {exc}", flush=True)
    st.stop()

try:
    _request_context: RequestContext = resolve_request_context(
        _deployment_context,
        facility_store=_facility_store,
        access_token=st.query_params.get("access", ""),
        requested_facility_id=st.query_params.get("facility", ""),
        allow_external_facility_access=ALLOW_EXTERNAL_FACILITY_ACCESS,
        default_allowed_scales=tuple(legacy.ALLOWED_SCALES),
        default_research_mode=bool(legacy.RESEARCH_MODE),
    )
except RuntimeError as exc:
    st.error(
        "この患者用URLは無効、期限切れ、または施設情報と一致しません。"
        "施設から案内された最新のQRコードをご利用ください。"
    )
    print(f"RD4 PATIENT ACCESS ERROR: {exc}", flush=True)
    st.stop()

st.session_state["_rd4_request_context"] = _request_context
st.session_state["_rd4_site_id"] = _request_context.deployment.site_id
st.session_state["_rd4_site_name"] = _request_context.deployment.site_name
st.session_state["_rd4_project_id"] = _request_context.deployment.project_id
st.session_state["_rd4_allowed_scales"] = _request_context.allowed_scales
st.session_state["_rd4_external_facility_mode"] = _request_context.external
st.session_state["_rd4_research_mode"] = _request_context.research_mode


def _current_deployment_context() -> DeploymentContext:
    current = st.session_state.get("_rd4_request_context")
    if not isinstance(current, RequestContext):
        raise RuntimeError("patient request context is unavailable")
    return current.deployment


# Streamlit reruns this script in the same Python process while the imported
# legacy module can remain cached. Keep the unmodified functions once, so
# wrappers never wrap previously wrapped functions.
if not hasattr(legacy, "_master_original_save_result"):
    legacy._master_original_save_result = legacy.save_result

_original_save_result = legacy._master_original_save_result


def _extra_value(instrument: str, name: str) -> str:
    return str(
        st.session_state.get(
            f"master_{name}_{instrument}",
            "",
        )
        or ""
    )


def save_result_with_master(row: dict) -> None:
    """Save under the server-validated facility identity for this session."""
    enriched = dict(row)
    instrument = str(enriched.get("instrument", "")).upper()
    request_context = st.session_state.get("_rd4_request_context")
    if not isinstance(request_context, RequestContext):
        st.error(
            "施設情報を確認できないため送信できません。"
            "QRコードからもう一度開いてください。"
        )
        st.stop()
    if instrument not in set(request_context.allowed_scales):
        st.error("この施設では選択した質問票を利用できません。")
        st.stop()
    active_context = request_context.deployment
    enriched.update(
        {
            "source_app": "RD4",
            "source_version": enriched.get("app_version", ""),
            "visit_type": _extra_value(instrument, "visit_type"),
            "treatment_context": _extra_value(
                instrument,
                "treatment_context",
            ),
            "responder_role": _extra_value(
                instrument,
                "responder_role",
            ),
        }
    )

    if _pro_store is None:
        log_save_result(
            enriched,
            active_context,
            save_result="rejected_master_db_unavailable",
        )
        st.error(
            "マスターデータベースへ接続できないため送信を完了できません。"
            "時間をおいて再度お試しください。"
        )
        st.stop()

    db_started = time.perf_counter()
    try:
        # Final mutation before persistence: submitted tenant fields can never
        # override the server-validated token/deployment context.
        enriched = prepare_master_record(enriched, active_context)
        inserted = _pro_store.save_row(
            enriched,
            facility_id=active_context.site_id,
            project_id=active_context.project_id,
        )
        print(
            f"MASTER_DB_SECONDS={time.perf_counter() - db_started:.3f}",
            flush=True,
        )
        log_save_result(
            enriched,
            active_context,
            save_result="inserted" if inserted else "duplicate",
        )
    except Exception as exc:
        print(
            f"MASTER_DB_SECONDS={time.perf_counter() - db_started:.3f}",
            flush=True,
        )
        print("MASTER DB SAVE ERROR:", repr(exc), flush=True)
        log_save_result(enriched, active_context, save_result="error")
        st.error(
            "マスターデータベースへ保存できなかったため、"
            "送信は完了していません。時間をおいて再度お試しください。"
        )
        st.stop()

legacy.save_result = save_result_with_master


if not hasattr(legacy, "_master_original_get_previous_adct"):
    legacy._master_original_get_previous_adct = legacy.get_previous_adct


def get_previous_adct_from_facility(patient_code: str):
    if _pro_store is None:
        return legacy._master_original_get_previous_adct(patient_code)
    active_context = _current_deployment_context()
    return _pro_store.latest_score(
        patient_code,
        facility_id=active_context.site_id,
        scale="ADCT",
    )


legacy.get_previous_adct = get_previous_adct_from_facility


# Render Master Database is now the authoritative destination for RD4.
# The legacy Google endpoints can be slow or unavailable and previously kept
# Streamlit waiting before it rendered the submission-complete screen.
# Keep their call sites compatible, but return immediately.
def skip_legacy_google_backup(row: dict) -> bool:
    print(
        "LEGACY GOOGLE BACKUP: skipped; "
        "Render Master Database is authoritative",
        flush=True,
    )
    return True


legacy.send_to_google_form = skip_legacy_google_backup
legacy.send_to_google_sheet = skip_legacy_google_backup


def extend_renderer(original_renderer, instrument: str):
    def wrapped(language: str):
        result = original_renderer(language)

        title = (
            "追加情報（任意）"
            if language == "日本語"
            else "Additional information (optional)"
        )

        with st.expander(title):
            st.selectbox(
                (
                    "受診区分"
                    if language == "日本語"
                    else "Visit type"
                ),
                (
                    [
                        "",
                        "初回",
                        "定期再診",
                        "治療変更後",
                        "臨時相談",
                        "その他",
                    ]
                    if language == "日本語"
                    else [
                        "",
                        "First visit",
                        "Routine follow-up",
                        "After treatment change",
                        "Unscheduled consultation",
                        "Other",
                    ]
                ),
                key=f"master_visit_type_{instrument}",
                help=(
                    "氏名や診察券番号などの個人情報は入力しないでください。"
                    if language == "日本語"
                    else "Do not enter direct personal identifiers."
                ),
            )

            st.selectbox(
                (
                    "治療状況"
                    if language == "日本語"
                    else "Treatment context"
                ),
                (
                    [
                        "",
                        "治療継続中",
                        "治療開始後",
                        "治療変更後",
                        "治療中断中",
                        "不明",
                    ]
                    if language == "日本語"
                    else [
                        "",
                        "Ongoing treatment",
                        "After treatment start",
                        "After treatment change",
                        "Treatment interrupted",
                        "Unknown",
                    ]
                ),
                key=f"master_treatment_context_{instrument}",
            )

            st.selectbox(
                (
                    "回答者"
                    if language == "日本語"
                    else "Responder"
                ),
                (
                    [
                        "",
                        "本人",
                        "家族・代理",
                        "医療者の入力補助",
                    ]
                    if language == "日本語"
                    else [
                        "",
                        "Patient",
                        "Family/proxy",
                        "Assisted by clinical staff",
                    ]
                ),
                key=f"master_responder_role_{instrument}",
            )

            st.caption(
                (
                    "これらはMaster Databaseの拡張項目として保存され、"
                    "未選択でも送信できます。"
                )
                if language == "日本語"
                else (
                    "These optional fields are stored in the extensible "
                    "Master Database schema."
                )
            )

        return result

    wrapped.__name__ = (
        f"master_extended_{instrument.lower()}"
    )

    return wrapped


def install_renderer(
    renderer_name: str,
    instrument: str,
) -> None:
    """
    Install exactly one wrapper even after repeated Streamlit reruns.
    """

    original_attr = (
        f"_master_original_{renderer_name}"
    )

    if not hasattr(
        legacy,
        original_attr,
    ):
        setattr(
            legacy,
            original_attr,
            getattr(
                legacy,
                renderer_name,
            ),
        )

    original_renderer = getattr(
        legacy,
        original_attr,
    )

    setattr(
        legacy,
        renderer_name,
        extend_renderer(
            original_renderer,
            instrument,
        ),
    )


install_renderer(
    "render_adct",
    "ADCT",
)
install_renderer(
    "render_dlqi",
    "DLQI",
)
install_renderer(
    "render_uct",
    "UCT",
)


if __name__ == "__main__":
    legacy.main()
