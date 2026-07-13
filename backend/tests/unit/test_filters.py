import pytest

from reviewerfinder.models import (
    EmailVerificationStatus,
    InstitutionType,
    Scholar,
    Zone,
)
from reviewerfinder.rules.filters import (
    MIN_HINDEX_ZONE_1,
    MIN_HINDEX_ZONE_2,
    MIN_RECENT_PAPERS,
    hindex_ok,
    institution_ok,
    passes_all_hard_rules,
    recent_pubs_ok,
    zone_ok,
)


def make_scholar(**overrides) -> Scholar:
    defaults = dict(
        id="A1",
        display_name="Jane Doe",
        works_count_last_5y=MIN_RECENT_PAPERS,
        current_institution_type=InstitutionType.EDUCATION,
        zone=Zone.ZONE_1,
        h_index=MIN_HINDEX_ZONE_1,
        email="jane@example.edu",
        email_verification_status=EmailVerificationStatus.UNVERIFIED,
    )
    defaults.update(overrides)
    return Scholar(**defaults)


def test_recent_pubs_boundary_pass():
    assert recent_pubs_ok(make_scholar(works_count_last_5y=MIN_RECENT_PAPERS)) is True


def test_recent_pubs_boundary_fail():
    assert recent_pubs_ok(make_scholar(works_count_last_5y=MIN_RECENT_PAPERS - 1)) is False


def test_institution_ok_education():
    assert institution_ok(make_scholar(current_institution_type=InstitutionType.EDUCATION)) is True


def test_institution_ok_company_fails():
    assert institution_ok(make_scholar(current_institution_type=InstitutionType.COMPANY)) is False


@pytest.mark.parametrize(
    "zone,h_index,expected",
    [
        (Zone.ZONE_1, MIN_HINDEX_ZONE_1, True),
        (Zone.ZONE_1, MIN_HINDEX_ZONE_1 - 1, False),
        (Zone.ZONE_2, MIN_HINDEX_ZONE_2, True),
        (Zone.ZONE_2, MIN_HINDEX_ZONE_2 - 1, False),
        (Zone.ZONE_3, 100, False),  # zone 3 never passes regardless of h-index
    ],
)
def test_hindex_ok_boundaries(zone, h_index, expected):
    assert hindex_ok(make_scholar(zone=zone, h_index=h_index)) is expected


def test_zone_ok_rejects_zone_3_and_excluded():
    assert zone_ok(make_scholar(zone=Zone.ZONE_3)) is False
    assert zone_ok(make_scholar(zone=Zone.EXCLUDED)) is False


def test_passes_all_hard_rules_happy_path():
    passed, reasons = passes_all_hard_rules(make_scholar())
    assert passed is True
    assert reasons == []


def test_passes_all_hard_rules_reports_every_failure_simultaneously():
    scholar = make_scholar(
        zone=Zone.ZONE_3,
        current_institution_type=InstitutionType.COMPANY,
        works_count_last_5y=2,
        h_index=1,
        email_verification_status=EmailVerificationStatus.NOT_FOUND,
    )
    passed, reasons = passes_all_hard_rules(scholar, check_email=True)
    assert passed is False
    assert any(r.startswith("disallowed_country_zone") for r in reasons)
    assert any(r.startswith("not_academic_institution") for r in reasons)
    assert any(r.startswith("insufficient_recent_papers") for r in reasons)
    assert any(r == "no_email_found" for r in reasons)


def test_passes_all_hard_rules_ignores_email_by_default():
    """Phase 1: email discovery isn't built yet, so the default aggregate
    must not gate on it (every scholar starts with NOT_FOUND)."""
    scholar = make_scholar(email_verification_status=EmailVerificationStatus.NOT_FOUND)
    passed, reasons = passes_all_hard_rules(scholar)
    assert passed is True
    assert reasons == []


def test_passes_all_hard_rules_require_verified_email_flag():
    scholar = make_scholar(email_verification_status=EmailVerificationStatus.UNVERIFIED)
    passed_default, _ = passes_all_hard_rules(scholar, check_email=True)
    passed_strict, reasons_strict = passes_all_hard_rules(
        scholar, check_email=True, require_verified_email=True
    )
    assert passed_default is True
    assert passed_strict is False
    assert "no_email_found" in reasons_strict
