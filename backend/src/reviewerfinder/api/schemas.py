from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from reviewerfinder.models import KeywordSet, Paper, Scholar


class SearchRequest(BaseModel):
    title: str
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    max_pages: int = 2
    results_per_set: int = 5


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
