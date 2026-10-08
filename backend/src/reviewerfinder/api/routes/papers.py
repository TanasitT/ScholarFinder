from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from reviewerfinder.api import jobs
from reviewerfinder.api.deps import (
    check_ollama_reachable,
    get_db_path,
    get_keyword_set_repository,
    get_match_repository,
    get_openalex_client,
    get_paper_repository,
    get_scholar_repository,
    get_semantic_scholar_client,
)
from reviewerfinder.api.schemas import (
    KeywordSetResult,
    PaperDetail,
    PaperSummary,
    RankedScholar,
    SearchJobStatus,
    SearchRequest,
    SearchResponse,
)
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.repository import (
    KeywordSetRepository,
    MatchRepository,
    PaperRepository,
    ScholarRepository,
)
from reviewerfinder.pipeline import run_search
from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.get("", response_model=list[PaperSummary])
def list_papers(
    paper_repo: PaperRepository = Depends(get_paper_repository),
    match_repo: MatchRepository = Depends(get_match_repository),
) -> list[PaperSummary]:
    papers = paper_repo.list_all()
    return [
        PaperSummary(
            id=paper.id,
            title=paper.title,
            run_date=paper.run_date,
            passing_count=match_repo.passing_count(paper.id),
        )
        for paper in papers
    ]


def _build_keyword_set_results(
    paper_id: int,
    keyword_set_repo: KeywordSetRepository,
    scholar_repo: ScholarRepository,
    match_repo: MatchRepository,
    limit: int = 5,
) -> list[KeywordSetResult]:
    results = []
    for ks in keyword_set_repo.list_for_paper(paper_id):
        rows = match_repo.top_candidates_for_keyword_set(ks.id, limit=limit)
        ranked: list[RankedScholar] = []
        for row in rows:
            scholar = scholar_repo.get(row["scholar_id"])
            if scholar is None:
                continue
            ranked.append(
                RankedScholar(
                    scholar=scholar,
                    relevance_score=row["relevance_score"],
                    rank_position=row["rank_position"],
                )
            )
        results.append(KeywordSetResult(keyword_set=ks, evaluated_count=len(ranked), passing_scholars=ranked))
    return results


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(
    paper_id: int,
    paper_repo: PaperRepository = Depends(get_paper_repository),
    keyword_set_repo: KeywordSetRepository = Depends(get_keyword_set_repository),
    scholar_repo: ScholarRepository = Depends(get_scholar_repository),
    match_repo: MatchRepository = Depends(get_match_repository),
) -> PaperDetail:
    paper = paper_repo.get(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"No paper with id {paper_id}")

    keyword_set_results = _build_keyword_set_results(paper_id, keyword_set_repo, scholar_repo, match_repo)
    return PaperDetail(paper=paper, keyword_set_results=keyword_set_results)


@router.post("/search", response_model=SearchJobStatus, status_code=202)
def start_search(
    body: SearchRequest,
    db_path: Path = Depends(get_db_path),
    openalex_client: OpenAlexClient = Depends(get_openalex_client),
    s2_client: SemanticScholarClient = Depends(get_semantic_scholar_client),
) -> SearchJobStatus:
    """Kicks off a search in a background thread and returns immediately
    with a job id -- decomposing the paper into 5 keyword sets and then
    running each end-to-end can take minutes, so this can't be a single
    blocking request if the frontend wants to show progress. Poll
    GET /search/{job_id} for status.

    Ollama reachability is only checked when the request doesn't supply its
    own manual_keyword_sets -- a plain call rather than a Depends(), since
    whether it's needed depends on the request body, which Depends() can't
    express without duplicating the parsing.
    """
    if body.manual_keyword_sets is None:
        check_ollama_reachable()

    job = jobs.create_job()

    def _run() -> None:
        try:
            result = run_search(
                title=body.title,
                abstract=body.abstract,
                keywords=body.keywords,
                db_path=db_path,
                openalex_client=openalex_client,
                ollama_base_url=settings.ollama_base_url,
                ollama_model=settings.ollama_model,
                s2_client=s2_client,
                staleness_months=settings.scholar_staleness_months,
                max_openalex_pages=body.max_pages,
                results_per_set=body.results_per_set,
                manual_keyword_sets=body.manual_keyword_sets,
                on_progress=jobs.progress_callback(job.job_id),
            )
            response = SearchResponse(
                paper=result.paper,
                evaluated_count=result.evaluated_count,
                keyword_set_results=[
                    KeywordSetResult(
                        keyword_set=set_result.keyword_set,
                        evaluated_count=set_result.evaluated_count,
                        passing_scholars=[
                            RankedScholar(scholar=scholar, relevance_score=score, rank_position=position)
                            for position, (scholar, score) in enumerate(set_result.passing_scholars, start=1)
                        ],
                    )
                    for set_result in result.keyword_set_results
                ],
            )
            jobs.mark_done(job.job_id, response)
        except Exception as e:
            logger.exception("Search job %s failed", job.job_id)
            jobs.mark_error(job.job_id, f"{type(e).__name__}: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return job


@router.get("/search/{job_id}", response_model=SearchJobStatus)
def get_search_job(job_id: str) -> SearchJobStatus:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No search job with id {job_id}")
    return job
