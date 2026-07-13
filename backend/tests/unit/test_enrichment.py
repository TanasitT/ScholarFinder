from datetime import datetime

from reviewerfinder.discovery.enrichment import carry_over_email
from reviewerfinder.models import EmailVerificationStatus, Scholar


def make_scholar(**overrides) -> Scholar:
    defaults = dict(id="A1", display_name="Jane Doe")
    defaults.update(overrides)
    return Scholar(**defaults)


def test_carry_over_email_preserves_previously_found_email():
    checked_at = datetime(2026, 1, 1)
    old = make_scholar(
        email="jane@mit.edu",
        email_source="openalex_oa:https://example.edu/paper",
        email_verification_status=EmailVerificationStatus.UNVERIFIED,
        email_checked_at=checked_at,
    )
    new = make_scholar()  # freshly rebuilt from OpenAlex, no email fields set

    result = carry_over_email(new, old)

    assert result.email == "jane@mit.edu"
    assert result.email_source == "openalex_oa:https://example.edu/paper"
    assert result.email_verification_status == EmailVerificationStatus.UNVERIFIED
    assert result.email_checked_at == checked_at


def test_carry_over_email_with_no_old_scholar_is_a_noop():
    new = make_scholar()
    result = carry_over_email(new, None)
    assert result is new
    assert result.email_verification_status == EmailVerificationStatus.NOT_FOUND
