from master_store import canonical_row


def test_server_facility_context_overrides_submitted_site_values():
    row = canonical_row(
        {
            "site_id": "ATTACKER_SITE",
            "facility_id": "ATTACKER_FACILITY",
            "project_id": "ATTACKER_PROJECT",
            "visit_code": "AD001",
            "instrument": "ADCT",
            "timestamp": "2026-07-27T09:00:00+09:00",
            "total_score": 4,
        },
        facility_id="VALIDATED_CLINIC",
        project_id="VALIDATED_PROJECT",
    )
    assert row["facility_id"] == "VALIDATED_CLINIC"
    assert row["project_id"] == "VALIDATED_PROJECT"
