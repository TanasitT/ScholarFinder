from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from reviewerfinder.models import KeywordSet, Paper, Scholar


def _normalize_country_codes(codes: list[str] | None) -> list[str] | None:
    if not codes:
        return None
    normalized = [c.strip().upper() for c in codes]
    for code in normalized:
        if len(code) != 2 or not code.isalpha():
            raise ValueError(f"'{code}' is not a 2-letter ISO alpha-2 country code")
    return normalized


class SearchRequest(BaseModel):
    title: str
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    max_pages: int = 2
    results_per_set: int = 10
    allowed_countries: list[str] | None = None
    excluded_countries: list[str] | None = None
    manual_keyword_sets: list[list[str]] | None = None

    @field_validator("allowed_countries", "excluded_countries")
    @classmethod
    def _validate_country_codes(cls, v: list[str] | None) -> list[str] | None:
        return _normalize_country_codes(v)

    @field_validator("manual_keyword_sets")
    @classmethod
    def _validate_manual_keyword_sets(cls, v: list[list[str]] | None) -> list[list[str]] | None:
        if v is None:
            return None
        # Mirrors pipeline.py::_validate_manual_keyword_sets's bounds, checked
        # here too so a malformed request gets a fast 422 instead of starting
        # a background job that immediately errors out.
        from reviewerfinder.pipeline import (
            MAX_MANUAL_KEYWORD_SETS,
            MIN_MANUAL_KEYWORD_SETS,
            _validate_manual_keyword_sets,
        )

        if not (MIN_MANUAL_KEYWORD_SETS <= len(v) <= MAX_MANUAL_KEYWORD_SETS):
            raise ValueError(
                f"manual_keyword_sets must have {MIN_MANUAL_KEYWORD_SETS}-{MAX_MANUAL_KEYWORD_SETS} groups, got {len(v)}"
            )
        return _validate_manual_keyword_sets(v)


class RankedScholar(BaseModel):
    scholar: Scholar
    relevance_score: float
    rank_position: int


class KeywordSetResult(BaseModel):
    keyword_set: KeywordSet
    evaluated_count: int
    passing_scholars: list[RankedScholar]


class SearchResponse(BaseModel):
    paper: Paper
    evaluated_count: int
    keyword_set_results: list[KeywordSetResult]


class PaperDetail(BaseModel):
    paper: Paper
    keyword_set_results: list[KeywordSetResult]


class SearchJobStatus(BaseModel):
    """Progress/result of a search running in a background thread.

    `stage` is "generating_keywords" once up front, then "set_<N>_<phase>"
    for N in 1..5 and phase one of discovering/enriching/filtering/
    email_hunt/ranking, then a final "done". `done`/`total` are only
    meaningful within the current stage -- they reset at each transition,
    they are not overall progress across the whole job.
    """

    job_id: str
    status: Literal["running", "done", "error"]
    stage: str
    done: int
    total: int
    result: SearchResponse | None = None
    error: str | None = None


class PaperSummary(BaseModel):
    id: int
    title: str
    run_date: date
    passing_count: int
