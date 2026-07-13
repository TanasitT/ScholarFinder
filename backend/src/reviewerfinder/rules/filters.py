from __future__ import annotations

from reviewerfinder.models import EmailVerificationStatus, InstitutionType, Scholar, Zone
from reviewerfinder.rules.zones import is_allowed_zone

MIN_RECENT_PAPERS = 8
MIN_HINDEX_ZONE_1 = 5
MIN_HINDEX_ZONE_2 = 10


def recent_pubs_ok(scholar: Scholar) -> bool:
    """8+ papers published in the last 5 years.

    `works_count_last_5y` is expected to already be computed (by
    discovery/enrichment.py, summing OpenAlex `counts_by_year` for the
    5 years ending at the paper's run_date) before this is called.
    """
    return (scholar.works_count_last_5y or 0) >= MIN_RECENT_PAPERS


def zone_ok(scholar: Scholar) -> bool:
    return is_allowed_zone(scholar.zone)


def institution_ok(scholar: Scholar) -> bool:
    return scholar.current_institution_type == InstitutionType.EDUCATION


def hindex_ok(scholar: Scholar) -> bool:
    h_index = scholar.h_index or 0
    if scholar.zone == Zone.ZONE_1:
        return h_index >= MIN_HINDEX_ZONE_1
    if scholar.zone == Zone.ZONE_2:
        return h_index >= MIN_HINDEX_ZONE_2
    return False


def email_ok(scholar: Scholar, *, require_verified_email: bool = False) -> bool:
    """Whether the email requirement is satisfied.

    Per the confirmed decision, automated verification is not wired up yet
    (email_verifier.py is a no-op returning `unverified`). By default this
    only requires that *some* email was found (status != NOT_FOUND) rather
    than requiring `verified`, so the pipeline stays usable until a real
    verification provider is configured. Pass require_verified_email=True
    once a provider is wired up to enforce the strict rule.
    """
    if require_verified_email:
        return scholar.email_verification_status == EmailVerificationStatus.VERIFIED
    return scholar.email_verification_status != EmailVerificationStatus.NOT_FOUND


def passes_all_hard_rules(
    scholar: Scholar, *, check_email: bool = False, require_verified_email: bool = False
) -> tuple[bool, list[str]]:
    """Evaluate every hard eligibility rule against a scholar.

    Returns (passed, fail_reasons). Every rule is checked (not short-circuited)
    so a rejected candidate's full set of failure reasons is captured for
    storage/auditability, e.g. for the chatbot to explain a rejection.

    `check_email` defaults to False because email discovery isn't built yet
    (Phase 2) — in Phase 1 every scholar has email_verification_status
    NOT_FOUND, so gating on it here would fail every candidate. Phase 2's
    pipeline should pass check_email=True once email_hunter.py is wired up.
    """
    fail_reasons: list[str] = []

    if not zone_ok(scholar):
        fail_reasons.append(f"disallowed_country_zone:{scholar.zone.value}")

    if not institution_ok(scholar):
        fail_reasons.append(
            f"not_academic_institution:{scholar.current_institution_type.value}"
        )

    if not recent_pubs_ok(scholar):
        fail_reasons.append(
            f"insufficient_recent_papers:{scholar.works_count_last_5y or 0}<{MIN_RECENT_PAPERS}"
        )

    # h-index rule depends on zone; if zone itself is disallowed, still report
    # the h-index shortfall using whichever zone-specific threshold would have
    # applied, for a fully informative rejection reason.
    if scholar.zone in (Zone.ZONE_1, Zone.ZONE_2) and not hindex_ok(scholar):
        threshold = MIN_HINDEX_ZONE_1 if scholar.zone == Zone.ZONE_1 else MIN_HINDEX_ZONE_2
        fail_reasons.append(f"hindex_below_threshold:{scholar.h_index or 0}<{threshold}")

    if check_email and not email_ok(scholar, require_verified_email=require_verified_email):
        fail_reasons.append("no_email_found")

    return (len(fail_reasons) == 0, fail_reasons)
