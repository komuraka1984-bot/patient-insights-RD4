from conference_demo import (
    allowed_scales,
    anonymous_code_digits,
    is_conference_demo,
    uc001_history_rows,
)


def test_conference_demo_is_uct_only_and_prefills_uc001():
    assert is_conference_demo("conference_demo") is True
    assert allowed_scales("CONFERENCE_DEMO", ("ADCT", "DLQI", "UCT")) == (
        "UCT",
    )
    assert anonymous_code_digits("CONFERENCE_DEMO") == "001"


def test_normal_facility_defaults_are_unchanged():
    defaults = ("ADCT", "DLQI", "UCT")
    assert is_conference_demo("KRCH_HOSP") is False
    assert allowed_scales("KRCH_HOSP", defaults) == defaults
    assert anonymous_code_digits("KRCH_HOSP") == ""


def test_uc001_history_has_fixed_half_year_and_two_month_points():
    rows = uc001_history_rows()
    assert [row["anonymous_id"] for row in rows] == ["UC001", "UC001"]
    assert [row["scale"] for row in rows] == ["UCT", "UCT"]
    assert [row["submitted_at"] for row in rows] == [
        "2026-02-18T09:00:00+09:00",
        "2026-06-18T09:00:00+09:00",
    ]
    assert [row["total_score"] for row in rows] == [3, 7]
    assert len({row["submission_id"] for row in rows}) == 2
