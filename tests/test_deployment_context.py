import pytest

from deployment_context import (
    DeploymentContext,
    prepare_master_record,
    resolve_deployment_context,
    resolve_request_context,
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


class Facility:
    facility_id = "IWATA"
    facility_name = "Iwata Dermatology"
    project_id = "SHIRABEO_FLOW_2026"
    allowed_scales = ("DLQI", "UCT")
    usage_mode = "clinical_workflow"


class FacilityStore:
    def resolve_patient_access_token(self, token):
        return Facility() if token == "valid-opaque-token" else None


def test_valid_patient_token_resolves_external_facility_server_side():
    context = resolve_request_context(
        deployment("KRCH_DERM"),
        facility_store=FacilityStore(),
        access_token="valid-opaque-token",
        requested_facility_id="IWATA",
    )

    assert context.deployment == DeploymentContext(
        site_id="IWATA",
        site_name="Iwata Dermatology",
        project_id="SHIRABEO_FLOW_2026",
    )
    assert context.allowed_scales == ("DLQI", "UCT")
    assert context.external is True
    assert context.research_mode is False


def test_invalid_patient_token_never_falls_back_to_krch():
    with pytest.raises(RuntimeError, match="token"):
        resolve_request_context(
            deployment("KRCH_DERM"),
            facility_store=FacilityStore(),
            access_token="invalid-token",
            requested_facility_id="IWATA",
        )


def test_dedicated_krch_entrance_rejects_external_token_routing():
    with pytest.raises(RuntimeError, match="dedicated entrance"):
        resolve_request_context(
            deployment("KRCH_DERM"),
            facility_store=FacilityStore(),
            access_token="valid-opaque-token",
            allow_external_facility_access=False,
        )


def test_dedicated_conference_entrance_keeps_server_facility():
    context = resolve_request_context(
        deployment("CONFERENCE_DEMO"),
        facility_store=FacilityStore(),
        allow_external_facility_access=False,
    )
    assert context.deployment.site_id == "CONFERENCE_DEMO"
    assert context.external is False


def test_facility_hint_must_match_token_resolved_facility():
    with pytest.raises(RuntimeError, match="does not match"):
        resolve_request_context(
            deployment("KRCH_DERM"),
            facility_store=FacilityStore(),
            access_token="valid-opaque-token",
            requested_facility_id="OTHER_CLINIC",
        )


def test_facility_hint_without_token_cannot_select_external_tenant():
    with pytest.raises(RuntimeError, match="requires"):
        resolve_request_context(
            deployment("KRCH_DERM"),
            facility_store=FacilityStore(),
            requested_facility_id="IWATA",
        )
