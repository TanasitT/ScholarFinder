from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Zone(str, Enum):
    ZONE_1 = "zone_1"
    ZONE_2 = "zone_2"
    ZONE_3 = "zone_3"
    EXCLUDED = "excluded"  # e.g. Egypt, Saudi Arabia, or unmapped country


class InstitutionType(str, Enum):
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    COMPANY = "company"
    ARCHIVE = "archive"
    NONPROFIT = "nonprofit"
    GOVERNMENT = "government"
    FACILITY = "facility"
    OTHER = "other"
    UNKNOWN = "unknown"


class EmailVerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_FOUND = "not_found"


class ProfileConfirmationStatus(str, Enum):
    CONFIRMED_VIA_ORCID = "confirmed_via_orcid"
    NEEDS_REVIEW = "needs_review"


class ResearchTopic(BaseModel):
    topic: str
    share: float = 0.0


class AffiliationRecord(BaseModel):
    institution_name: str
    country_code: str | None = None
    institution_type: InstitutionType = InstitutionType.UNKNOWN
    year_start: int | None = None
    year_end: int | None = None


class Paper(BaseModel):
    id: int | None = None
    title: str
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    run_date: date
    notes: str | None = None
    created_at: datetime | None = None


class Scholar(BaseModel):
    id: str  # OpenAlex author ID when available, else a generated internal id
    display_name: str
    orcid: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None

    h_index: int | None = None
    h_index_source: str | None = None  # "openalex" | "semantic_scholar" | "manual"
    works_count_total: int | None = None
    works_count_last_5y: int | None = None

    current_institution_name: str | None = None
    current_institution_country_code: str | None = None
    current_institution_type: InstitutionType = InstitutionType.UNKNOWN
    zone: Zone = Zone.EXCLUDED

    research_topics: list[ResearchTopic] = Field(default_factory=list)

    email: str | None = None
    email_verification_status: EmailVerificationStatus = EmailVerificationStatus.NOT_FOUND
    email_source: str | None = None
    email_checked_at: datetime | None = None

    gscholar_search_url: str | None = None
    scopus_search_url: str | None = None
    profile_confirmation_status: ProfileConfirmationStatus = ProfileConfirmationStatus.NEEDS_REVIEW

    last_checked_at: datetime | None = None
    raw_openalex_json: str | None = None
    raw_s2_json: str | None = None


class FitResult(BaseModel):
    scholar_id: str
    paper_id: int
    passed: bool
    fail_reasons: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0


class PaperScholarMatch(BaseModel):
    id: int | None = None
    paper_id: int
    keyword_set_id: int | None = None
    scholar_id: str
    relevance_score: float = 0.0
    passed_hard_rules: bool = False
    fail_reasons: list[str] = Field(default_factory=list)
    rank_position: int | None = None


class KeywordSet(BaseModel):
    """One of 5 distinct 3-keyword search angles Claude derives from a
    paper's title/abstract/keywords -- see discovery/keyword_summarizer.py.
    """

    id: int | None = None
    paper_id: int | None = None
    set_index: int  # 1..5, the order Claude proposed them in
    label: str  # short theme name, e.g. "Methodology"
    keywords: list[str]  # exactly 3
