from datetime import datetime, timezone
from pathlib import Path

import pytest

from facility_access import (
    FacilityStore,
    hash_password,
    verify_password,
)


def make_store(tmp_path: Path) -> FacilityStore:
    return FacilityStore(
        database_url="",
        sqlite_path=tmp_path / "facility.sqlite3",
    )


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("long-enough-password")
    second = hash_password("long-enough-password")
    assert first != second
    assert verify_password("long-enough-password", first)
    assert not verify_password("wrong-password", first)


def test_create_login_and_patient_entry(tmp_path: Path):
    store = make_store(tmp_path)
    issued = store.create_facility(
        facility_name="External Clinic",
        facility_id="CLINIC_A",
        allowed_scales=("DLQI", "UCT"),
    )

    assert issued.facility.facility_id == "CLINIC_A"
    assert issued.staff_password not in str(store.list_facilities())
    assert issued.patient_access_token not in str(store.list_facilities())

    login = store.authenticate(
        "clinic_a",
        issued.staff_password,
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
    )
    assert login.ok is True
    assert login.facility is not None
    assert login.facility.authenticated is True
    assert login.facility.allowed_scales == ("DLQI", "UCT")

    assert store.resolve_patient_access(
        "CLINIC_A",
        issued.patient_access_token,
    )
    assert store.resolve_patient_access("CLINIC_A", "wrong-token") is None


def test_adct_requires_facility_specific_confirmation(tmp_path: Path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError, match="ADCT"):
        store.create_facility(
            facility_name="External AD Clinic",
            facility_id="CLINIC_AD",
            allowed_scales=("ADCT",),
            adct_license_status="not_confirmed",
        )

    issued = store.create_facility(
        facility_name="Licensed AD Clinic",
        facility_id="CLINIC_AD_OK",
        allowed_scales=("ADCT",),
        adct_license_status="confirmed",
    )
    assert issued.facility.allowed_scales == ("ADCT",)


def test_password_and_patient_token_rotation(tmp_path: Path):
    store = make_store(tmp_path)
    issued = store.create_facility(
        facility_name="Rotation Clinic",
        facility_id="ROTATE_A",
    )
    new_password = store.rotate_password("ROTATE_A")
    assert not store.authenticate(
        "ROTATE_A",
        issued.staff_password,
    ).ok
    assert store.authenticate("ROTATE_A", new_password).ok

    new_token = store.rotate_patient_access_token("ROTATE_A")
    assert store.resolve_patient_access(
        "ROTATE_A",
        issued.patient_access_token,
    ) is None
    assert store.resolve_patient_access("ROTATE_A", new_token)


def test_suspension_blocks_staff_and_patient_access(tmp_path: Path):
    store = make_store(tmp_path)
    issued = store.create_facility(
        facility_name="Suspended Clinic",
        facility_id="SUSPEND_A",
    )
    store.set_access_enabled("SUSPEND_A", enabled=False)

    login = store.authenticate("SUSPEND_A", issued.staff_password)
    assert login.ok is False
    assert login.reason == "access_disabled"
    assert store.resolve_patient_access(
        "SUSPEND_A",
        issued.patient_access_token,
    ) is None


def test_failed_logins_temporarily_lock_account(tmp_path: Path):
    store = make_store(tmp_path)
    issued = store.create_facility(
        facility_name="Lock Clinic",
        facility_id="LOCK_A",
    )
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    result = None
    for _ in range(5):
        result = store.authenticate("LOCK_A", "wrong-password", now=now)

    assert result is not None
    assert result.reason == "temporarily_locked"
    locked = store.authenticate("LOCK_A", issued.staff_password, now=now)
    assert locked.ok is False
    assert locked.reason == "temporarily_locked"


def test_stripe_ready_fields_and_event_idempotency(tmp_path: Path):
    store = make_store(tmp_path)
    store.create_facility(
        facility_name="Billing Clinic",
        facility_id="BILLING_A",
    )
    facility = store.update_billing(
        "BILLING_A",
        plan_code="flow_30000",
        billing_status="trialing",
        stripe_customer_id="cus_example",
        stripe_subscription_id="sub_example",
        stripe_price_id="price_example",
        current_period_end="2026-09-01T00:00:00+00:00",
    )
    assert facility.plan_code == "flow_30000"
    assert facility.billing_status == "trialing"
    assert facility.stripe_customer_id == "cus_example"
    assert facility.stripe_subscription_id == "sub_example"
    assert facility.stripe_price_id == "price_example"

    assert store.record_stripe_event(
        event_id="evt_1",
        event_type="customer.subscription.updated",
        facility_id="BILLING_A",
    )
    assert not store.record_stripe_event(
        event_id="evt_1",
        event_type="customer.subscription.updated",
        facility_id="BILLING_A",
    )
