from __future__ import annotations

import os
import time

import streamlit as st

import app as legacy
from facility_access import (
    FacilityStore,
    legacy_facility_context,
    normalize_facility_id,
)
from master_store import ProStore


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MASTER_REQUIRED = (
    os.getenv("MASTER_DB_REQUIRED", "true").strip().lower()
    not in {"0", "false", "no"}
)

_pro_store: ProStore | None = ProStore(DATABASE_URL) if DATABASE_URL else None

_default_site_id = legacy.SITE_ID
_default_site_name = legacy.SITE_NAME
_default_project_id = legacy.PROJECT_ID


@st.cache_resource
def get_facility_store() -> FacilityStore:
    return FacilityStore(DATABASE_URL)


def resolve_patient_facility():
    facility_param = str(st.query_params.get("facility", "") or "").strip()
    access_param = str(st.query_params.get("access", "") or "").strip()
    if not facility_param and not access_param:
        return legacy_facility_context(
            facility_id=_default_site_id,
            facility_name=_default_site_name,
            project_id=_default_project_id,
        )
    if not facility_param or not access_param:
        st.error(
            "施設専用URLが不完全です。受付で案内されたQRコードから"
            "もう一度アクセスしてください。"
        )
        st.stop()
    try:
        store = get_facility_store()
        context = store.resolve_patient_access(
            normalize_facility_id(facility_param),
            access_param,
        )
    except Exception as exc:
        print("FACILITY ENTRY ERROR:", repr(exc), flush=True)
        context = None
    if context is None:
        st.error(
            "この施設用URLは無効または停止中です。"
            "受付で最新のQRコードをご確認ください。"
        )
        st.stop()
    return context


_facility_context = resolve_patient_facility()
legacy.SITE_ID = _facility_context.facility_id
legacy.SITE_NAME = _facility_context.facility_name
legacy.PROJECT_ID = _facility_context.project_id or _default_project_id
legacy.PROJECT_PHASE = (
    "RESEARCH"
    if _facility_context.usage_mode == "research"
    else "FLOW"
)
legacy.RESEARCH_MODE = _facility_context.usage_mode == "research"
legacy.EXTERNAL_FACILITY_MODE = _facility_context.external
legacy.ALLOWED_SCALES = _facility_context.allowed_scales
legacy.FACILITY_CONTACT = (
    "contact@shirabeo.com"
    if _facility_context.external
    else legacy.FACILITY_CONTACT
)


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
    """
    Save locally first, then save to Master DB.

    This diagnostic version keeps the existing behavior unchanged and only
    prints separate timing values for the CSV backup and Master DB write.
    """

    if _facility_context.external:
        print(
            "CSV_SAVE_SECONDS=SKIPPED_EXTERNAL_FACILITY",
            flush=True,
        )
    else:
        # Preserve the existing Kanazawa Red Cross local fallback.
        csv_started = time.perf_counter()
        _original_save_result(dict(row))
        csv_elapsed = time.perf_counter() - csv_started
        print(
            f"CSV_SAVE_SECONDS={csv_elapsed:.3f}",
            flush=True,
        )

    enriched = dict(row)
    instrument = str(
        enriched.get("instrument", "")
    ).upper()

    enriched.update(
        {
            "source_app": "RD4",
            "source_version": enriched.get("app_version", ""),
            "visit_type": _extra_value(
                instrument,
                "visit_type",
            ),
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
        print(
            "MASTER_DB_SECONDS=SKIPPED",
            flush=True,
        )

        message = (
            "MASTER DB: DATABASE_URL is not set; "
            "submission kept in RD4 CSV backup"
        )
        print(
            message,
            flush=True,
        )

        if _facility_context.external:
            st.error(
                "マスターデータベースへ接続できないため送信を完了できません。"
                "時間をおいて再度お試しください。"
            )
            st.stop()
        if MASTER_REQUIRED:
            st.warning(
                "回答はRD4内に保存されましたが、"
                "マスターデータベースへの転送を確認できませんでした。"
                "管理者が接続設定を確認してください。"
            )

        return

    db_started = time.perf_counter()

    try:
        inserted = _pro_store.save_row(
            enriched,
            facility_id=legacy.SITE_ID,
            project_id=legacy.PROJECT_ID,
        )

        db_elapsed = time.perf_counter() - db_started

        print(
            f"MASTER_DB_SECONDS={db_elapsed:.3f}",
            flush=True,
        )
        print(
            "MASTER DB:",
            "inserted" if inserted else "duplicate",
            flush=True,
        )

    except Exception as exc:
        db_elapsed = time.perf_counter() - db_started

        print(
            f"MASTER_DB_SECONDS={db_elapsed:.3f}",
            flush=True,
        )
        print(
            "MASTER DB SAVE ERROR:",
            repr(exc),
            flush=True,
        )

        if _facility_context.external:
            st.error(
                "マスターデータベースへ保存できなかったため、"
                "送信は完了していません。時間をおいて再度お試しください。"
            )
            st.stop()

        # The Kanazawa Red Cross local CSV has already been written.
        st.warning(
            "回答はRD4内に保存されましたが、"
            "マスターデータベースへの転送で一時的な問題が発生しました。"
            "送信処理は継続します。"
        )


legacy.save_result = save_result_with_master


if not hasattr(legacy, "_master_original_get_previous_adct"):
    legacy._master_original_get_previous_adct = legacy.get_previous_adct


def get_previous_adct_from_facility(patient_code: str):
    if not _facility_context.external or _pro_store is None:
        return legacy._master_original_get_previous_adct(patient_code)
    return _pro_store.latest_score(
        patient_code,
        facility_id=legacy.SITE_ID,
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
        if instrument not in set(_facility_context.allowed_scales):
            st.error(
                "この施設では、この質問票は現在有効化されていません。"
            )
            st.stop()
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
