from __future__ import annotations

import os
import streamlit as st

import app as legacy
from master_store import ProStore

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MASTER_REQUIRED = os.getenv("MASTER_DB_REQUIRED", "true").strip().lower() not in {"0", "false", "no"}

_pro_store: ProStore | None = ProStore(DATABASE_URL) if DATABASE_URL else None
_original_save_result = legacy.save_result


def _extra_value(instrument: str, name: str) -> str:
    return str(st.session_state.get(f"master_{name}_{instrument}", "") or "")


def save_result_with_master(row: dict) -> None:
    """Keep the existing CSV schema and enrich only the shared Master DB row."""
    # Keep the local CSV byte-for-byte compatible with existing headers.
    _original_save_result(dict(row))

    enriched = dict(row)
    instrument = str(enriched.get("instrument", "")).upper()
    enriched.update(
        {
            "source_app": "RD4",
            "source_version": enriched.get("app_version", ""),
            "visit_type": _extra_value(instrument, "visit_type"),
            "treatment_context": _extra_value(instrument, "treatment_context"),
            "responder_role": _extra_value(instrument, "responder_role"),
        }
    )

    if _pro_store is None:
        if MASTER_REQUIRED:
            raise RuntimeError("DATABASE_URL is not configured for RD4 Master Database.")
        print("MASTER DB: DATABASE_URL is not set; existing backups only")
        return

    inserted = _pro_store.save_row(
        enriched,
        facility_id=legacy.SITE_ID,
        project_id=legacy.PROJECT_ID,
    )
    print("MASTER DB:", "inserted" if inserted else "duplicate")


legacy.save_result = save_result_with_master


def extend_renderer(original_renderer, instrument: str):
    def wrapped(language: str):
        result = original_renderer(language)
        title = "追加情報（任意）" if language == "日本語" else "Additional information (optional)"
        with st.expander(title):
            st.selectbox(
                "受診区分" if language == "日本語" else "Visit type",
                ["", "初回", "定期再診", "治療変更後", "臨時相談", "その他"]
                if language == "日本語"
                else ["", "First visit", "Routine follow-up", "After treatment change", "Unscheduled consultation", "Other"],
                key=f"master_visit_type_{instrument}",
                help="氏名や診察券番号などの個人情報は入力しないでください。"
                if language == "日本語"
                else "Do not enter direct personal identifiers.",
            )
            st.selectbox(
                "治療状況" if language == "日本語" else "Treatment context",
                ["", "治療継続中", "治療開始後", "治療変更後", "治療中断中", "不明"]
                if language == "日本語"
                else ["", "Ongoing treatment", "After treatment start", "After treatment change", "Treatment interrupted", "Unknown"],
                key=f"master_treatment_context_{instrument}",
            )
            st.selectbox(
                "回答者" if language == "日本語" else "Responder",
                ["", "本人", "家族・代理", "医療者の入力補助"]
                if language == "日本語"
                else ["", "Patient", "Family/proxy", "Assisted by clinical staff"],
                key=f"master_responder_role_{instrument}",
            )
            st.caption(
                "これらはMaster Databaseの拡張項目として保存され、未選択でも送信できます。"
                if language == "日本語"
                else "These optional fields are stored in the extensible Master Database schema."
            )
        return result
    return wrapped


legacy.render_adct = extend_renderer(legacy.render_adct, "ADCT")
legacy.render_dlqi = extend_renderer(legacy.render_dlqi, "DLQI")
legacy.render_uct = extend_renderer(legacy.render_uct, "UCT")


if __name__ == "__main__":
    legacy.main()
