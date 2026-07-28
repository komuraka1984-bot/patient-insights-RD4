from legal_documents import (
    PATIENT_TERMS_VERSION,
    PRIVACY_POLICY_VERSION,
    build_service_consent_record,
    patient_terms_markdown,
    privacy_policy_markdown,
)


COMMON = {
    "service_provider": "Shirabeo Labs",
    "facility_name": "Test Clinic",
    "contact_email": "contact@example.com",
}


def test_service_consent_record_is_versioned_and_timestamped():
    record = build_service_consent_record("2026-07-28 12:34:56")

    assert record["consent_checked"] is True
    assert record["terms_consent_checked"] is True
    assert record["privacy_policy_acknowledged"] is True
    assert record["patient_terms_version"] == PATIENT_TERMS_VERSION
    assert record["privacy_policy_version"] == PRIVACY_POLICY_VERSION
    assert record["terms_consent_timestamp"] == "2026-07-28 12:34:56"


def test_japanese_terms_cover_paid_service_and_separate_research_consent():
    terms = patient_terms_markdown("日本語", **COMMON)

    assert "弁護士レビュー用ドラフト" in terms
    assert "有償で提供される場合" in terms
    assert "研究参加への同意は別" in terms
    assert "緊急時" in terms
    assert PATIENT_TERMS_VERSION in terms


def test_japanese_privacy_policy_covers_required_review_topics():
    policy = privacy_policy_markdown(
        "日本語",
        hosting_region="Oregon, United States",
        **COMMON,
    )

    assert "匿名情報」とは限りません" in policy
    assert "契約、請求、プラン管理" in policy
    assert "Oregon, United States" in policy
    assert "保存期間・削除" in policy
    assert "弁護士確認事項" in policy
    assert PRIVACY_POLICY_VERSION in policy


def test_english_documents_are_available():
    terms = patient_terms_markdown("English", **COMMON)
    policy = privacy_policy_markdown(
        "English",
        hosting_region="Oregon, United States",
        **COMMON,
    )

    assert "Draft for legal review" in terms
    assert "paid agreement" in terms
    assert "separate from consent to participate in research" in terms
    assert "international processing" in policy
    assert "not necessarily legally anonymous" in policy
