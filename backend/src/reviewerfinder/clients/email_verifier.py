from __future__ import annotations

from reviewerfinder.models import EmailVerificationStatus


def verify_email(email: str) -> EmailVerificationStatus:
    """Verify a discovered email's deliverability.

    No paid verification provider is wired up yet (per project decision to
    defer that cost/setup). This deliberately always returns UNVERIFIED
    rather than VERIFIED or NOT_FOUND -- the email was found, just not
    confirmed deliverable. Swap this function's body for a real provider
    (Hunter.io/NeverBounce/ZeroBounce) later; no caller needs to change.
    """
    return EmailVerificationStatus.UNVERIFIED
