from reviewerfinder.clients.email_verifier import verify_email
from reviewerfinder.models import EmailVerificationStatus


def test_verify_email_always_returns_unverified():
    assert verify_email("jane@example.edu") == EmailVerificationStatus.UNVERIFIED
    assert verify_email("someone@company.com") == EmailVerificationStatus.UNVERIFIED
    assert verify_email("") == EmailVerificationStatus.UNVERIFIED
