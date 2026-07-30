import pytest

from deployment_context import (
    prepare_master_record,
    resolve_deployment_context,
)


def deployment(site_id: str):
    return resolve_deployment_context(
        {
            "SITE_ID": site_id,
            "SITE_NAME": "Test Dermatology Department",
            "PROJECT_ID": "RD_PRO_PILOT_2026",
        }
    )


def submitted_row() -> dict:
    return {
        "visit_code": "AD001",
        "instrument": "ADCT",
        "facility_id": "CLINIC_KOMURA",
        "site_id": "CLINIC_KOMURA",
        "project_id": "OTHER_PROJECT",
    }


def test_krch_deployment_overwrites_client_facility_fields():
    record = prepare_master_record(submitted_row(), deployment("KRCH_DERM"))
    assert record["facility_id"] == "KRCH_DERM"
    assert record["site_id"] == "KRCH_DERM"
    assert record["project_id"] == "RD_PRO_PILOT_2026"


def test_clinic_deployment_keeps_its_own_server_side_identity():
    record = prepare_master_record(submitted_row(), deployment("CLINIC_KOMURA"))
    assert record["facility_id"] == "CLINIC_KOMURA"


def test_missing_site_id_fails_before_persistence():
    with pytest.raises(RuntimeError, match="SITE_ID"):
        resolve_deployment_context(
            {
                "SITE_NAME": "Test Dermatology Department",
                "PROJECT_ID": "RD_PRO_PILOT_2026",
            }
        )
