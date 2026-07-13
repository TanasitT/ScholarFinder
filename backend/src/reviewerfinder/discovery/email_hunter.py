from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime

import requests
from pypdf import PdfReader

from reviewerfinder.clients.email_verifier import verify_email
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.models import EmailVerificationStatus, Scholar

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Addresses with these local-parts are deprioritized in favor of a
# personal-looking address when multiple emails appear on the same page.
_GENERIC_LOCALPARTS = {
    "info", "contact", "support", "admin", "webmaster",
    "noreply", "no-reply", "postmaster", "editor", "office",
}

MAX_RECENT_WORKS_TO_SCAN = 3
FETCH_TIMEOUT_SECONDS = 15
MAX_CONTENT_BYTES = 5_000_000
MAX_PDF_PAGES = 5


def _extract_emails_from_text(text: str) -> list[str]:
    return EMAIL_RE.findall(text or "")


def _name_tokens(display_name: str) -> list[str]:
    """Lowercase alphabetic name parts, dropping single/double-letter
    initials -- too short to check against an email local-part without
    false-positiving on nearly anything.
    """
    return [t.lower() for t in re.findall(r"[A-Za-z]+", display_name) if len(t) >= 3]


def _email_matches_name(email: str, name_tokens: list[str]) -> bool:
    localpart = re.sub(r"[^a-z]", "", email.split("@", 1)[0].lower())
    return any(token in localpart for token in name_tokens)


def _pick_best_email(candidates: list[str], display_name: str) -> str | None:
    """Only returns an email that plausibly belongs to *this* scholar --
    i.e. their own name appears in the email's local-part.

    A scraped page/PDF often lists several people's emails (co-authors,
    department staff, editors); the old behaviour of picking "the first
    non-generic-looking address" would silently attribute a stranger's
    email to this scholar, which is worse than finding no email at all --
    it directly violates the "never guess, only extract what genuinely
    belongs to this person" principle just as much as constructing one
    would. If no candidate's local-part contains this scholar's name,
    that's reported as not-found.
    """
    name_tokens = _name_tokens(display_name)
    if not name_tokens:
        return None
    for email in candidates:
        localpart = email.split("@", 1)[0].lower()
        if localpart in _GENERIC_LOCALPARTS:
            continue
        if _email_matches_name(email, name_tokens):
            return email
    return None


def _fetch_text(url: str, session: requests.Session) -> str | None:
    """Best-effort fetch + text extraction. Never raises -- scraping is
    inherently unreliable (dead links, blocked scrapers, odd content types),
    so any failure just means "no email found from this source", not a
    pipeline error.
    """
    try:
        resp = session.get(url, timeout=FETCH_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException:
        logger.debug("Failed to fetch %s for email scraping", url, exc_info=True)
        return None

    content_type = resp.headers.get("Content-Type", "")
    content = resp.content[:MAX_CONTENT_BYTES]

    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES])
        except Exception:
            logger.debug("Failed to extract PDF text from %s", url, exc_info=True)
            return None

    return content.decode("utf-8", errors="ignore")


def find_email_from_openalex_works(
    scholar: Scholar, openalex_client: OpenAlexClient, session: requests.Session
) -> tuple[str | None, str | None]:
    if not scholar.openalex_id:
        return None, None

    works = openalex_client.get_author_recent_works(scholar.openalex_id, limit=MAX_RECENT_WORKS_TO_SCAN)
    for work in works:
        oa_url = (work.get("open_access") or {}).get("oa_url")
        if not oa_url:
            continue
        text = _fetch_text(oa_url, session)
        if not text:
            continue
        best = _pick_best_email(_extract_emails_from_text(text), scholar.display_name)
        if best:
            return best, f"openalex_oa:{oa_url}"

    return None, None


def _homepage_from_raw_s2(raw_s2_json: str | None) -> str | None:
    if not raw_s2_json:
        return None
    try:
        data = json.loads(raw_s2_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return data.get("homepage")


def find_email_from_semantic_scholar_homepage(
    scholar: Scholar, session: requests.Session
) -> tuple[str | None, str | None]:
    homepage = _homepage_from_raw_s2(scholar.raw_s2_json)
    if not homepage:
        return None, None

    text = _fetch_text(homepage, session)
    if not text:
        return None, None

    best = _pick_best_email(_extract_emails_from_text(text), scholar.display_name)
    if best:
        return best, f"semantic_scholar_homepage:{homepage}"
    return None, None


def hunt_email(
    scholar: Scholar, openalex_client: OpenAlexClient, session: requests.Session | None = None
) -> Scholar:
    """Best-effort email discovery for one scholar.

    Never constructs/guesses an email from name+institution-domain patterns
    -- only extracts addresses that appear verbatim in scraped content
    (OpenAlex open-access papers, then the Semantic Scholar homepage as
    fallback). Sets scholar.email / email_source / email_verification_status
    / email_checked_at in place and returns it.
    """
    session = session or requests.Session()

    email, source = find_email_from_openalex_works(scholar, openalex_client, session)
    if not email:
        email, source = find_email_from_semantic_scholar_homepage(scholar, session)

    scholar.email_checked_at = datetime.now()
    if email:
        scholar.email = email
        scholar.email_source = source
        scholar.email_verification_status = verify_email(email)
    else:
        scholar.email_verification_status = EmailVerificationStatus.NOT_FOUND

    return scholar
