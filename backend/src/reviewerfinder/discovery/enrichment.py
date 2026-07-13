from __future__ import annotations

import json
import logging
from datetime import date, datetime

from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.models import (
    AffiliationRecord,
    InstitutionType,
    ResearchTopic,
    Scholar,
)
from reviewerfinder.rules.zones import zone_of

logger = logging.getLogger(__name__)

_INSTITUTION_TYPE_VALUES = {t.value for t in InstitutionType}


def _institution_type_from_openalex(raw_type: str | None) -> InstitutionType:
    if raw_type in _INSTITUTION_TYPE_VALUES:
        return InstitutionType(raw_type)
    return InstitutionType.UNKNOWN


def _works_count_last_5y(counts_by_year: list[dict], as_of: date) -> int:
    cutoff_year = as_of.year - 5
    return sum(
        entry.get("works_count", 0)
        for entry in counts_by_year
        if entry.get("year", 0) > cutoff_year
    )


def scholar_from_openalex_author(author: dict, run_date: date) -> Scholar:
    openalex_id = author["id"].rsplit("/", 1)[-1]
    summary_stats = author.get("summary_stats", {}) or {}
    last_known = author.get("last_known_institutions") or []
    primary_institution = last_known[0] if last_known else {}

    affiliations = author.get("affiliations") or []
    history = [
        AffiliationRecord(
            institution_name=(a.get("institution") or {}).get("display_name", "Unknown"),
            country_code=(a.get("institution") or {}).get("country_code"),
            institution_type=_institution_type_from_openalex(
                (a.get("institution") or {}).get("type")
            ),
            year_start=min(a.get("years", []), default=None),
            year_end=max(a.get("years", []), default=None),
        )
        for a in affiliations
    ]

    country_code = primary_institution.get("country_code")
    zone = zone_of(country_code)

    topics = [
        ResearchTopic(topic=t.get("display_name", ""), share=t.get("value", t.get("count", 0)) or 0)
        for t in (author.get("topics") or [])[:15]
    ]

    ids = author.get("ids", {}) or {}
    orcid = ids.get("orcid")
    if orcid:
        orcid = orcid.rsplit("/", 1)[-1]

    scholar = Scholar(
        id=openalex_id,
        display_name=author.get("display_name", "Unknown"),
        orcid=orcid,
        openalex_id=openalex_id,
        h_index=summary_stats.get("h_index"),
        h_index_source="openalex",
        works_count_total=author.get("works_count"),
        works_count_last_5y=_works_count_last_5y(author.get("counts_by_year") or [], run_date),
        current_institution_name=primary_institution.get("display_name"),
        current_institution_country_code=country_code,
        current_institution_type=_institution_type_from_openalex(primary_institution.get("type")),
        zone=zone,
        research_topics=topics,
        gscholar_search_url=_gscholar_url(author.get("display_name", "")),
        scopus_search_url=_scopus_url(author.get("display_name", "")),
        last_checked_at=datetime.now(),
    )
    return scholar, history


def carry_over_email(new_scholar: Scholar, old_scholar: Scholar | None) -> Scholar:
    """Preserve previously-discovered email data across a core-data refresh.

    scholar_from_openalex_author() always builds a brand-new Scholar with
    email fields at their defaults (None/NOT_FOUND) -- without this, every
    staleness-triggered refresh would silently discard prior email-hunting
    work. Called by every code path that rebuilds a scholar from a fresh
    OpenAlex fetch (pipeline.py, cli.py refresh, chatbot check_scholar_fit).
    """
    if old_scholar is None:
        return new_scholar
    new_scholar.email = old_scholar.email
    new_scholar.email_source = old_scholar.email_source
    new_scholar.email_verification_status = old_scholar.email_verification_status
    new_scholar.email_checked_at = old_scholar.email_checked_at
    return new_scholar


def _gscholar_url(name: str) -> str:
    from urllib.parse import quote_plus

    return f"https://scholar.google.com/scholar?q={quote_plus(name)}"


def _scopus_url(name: str) -> str:
    from urllib.parse import quote_plus

    return f"https://www.scopus.com/results/authorNamesList.uri?query={quote_plus(name)}"


def cross_check_with_semantic_scholar(scholar: Scholar, s2_client: SemanticScholarClient) -> Scholar:
    """Look up the scholar on Semantic Scholar (by name) and record their S2 ID
    plus their full raw match as JSON (so email_hunter.py can later read the
    `homepage` field out of it); logs h-index disagreement but does not let
    it override the OpenAlex value (OpenAlex remains authoritative).
    """
    candidates = s2_client.search_author_by_name(scholar.display_name)
    match = _best_name_match(candidates, scholar)
    if not match:
        return scholar

    scholar.semantic_scholar_id = match.get("authorId")
    scholar.raw_s2_json = json.dumps(match)

    s2_hindex = match.get("hIndex")
    if s2_hindex is not None and scholar.h_index is not None and abs(s2_hindex - scholar.h_index) > 3:
        logger.warning(
            "h-index disagreement for %s: OpenAlex=%s vs Semantic Scholar=%s (keeping OpenAlex value)",
            scholar.display_name,
            scholar.h_index,
            s2_hindex,
        )

    return scholar


def _best_name_match(candidates: list[dict], scholar: Scholar) -> dict | None:
    for candidate in candidates:
        if candidate.get("name", "").strip().lower() == scholar.display_name.strip().lower():
            return candidate
    return candidates[0] if candidates else None
