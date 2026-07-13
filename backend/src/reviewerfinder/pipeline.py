from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.repository import (
    KeywordSetRepository,
    MatchRepository,
    PaperRepository,
    ScholarRepository,
)
from reviewerfinder.discovery.candidate_finder import find_candidate_openalex_author_ids
from reviewerfinder.discovery.email_hunter import hunt_email
from reviewerfinder.discovery.enrichment import (
    carry_over_email,
    cross_check_with_semantic_scholar,
    scholar_from_openalex_author,
)
from reviewerfinder.discovery.keyword_summarizer import generate_keyword_sets
from reviewerfinder.models import EmailVerificationStatus, KeywordSet, Paper, Scholar
from reviewerfinder.rules.filters import passes_all_hard_rules
from reviewerfinder.rules.ranking import rank_scholars

logger = logging.getLogger(__name__)


@dataclass
class KeywordSetResult:
    keyword_set: KeywordSet
    passing_scholars: list[tuple[Scholar, float]]
    evaluated_count: int


@dataclass
class SearchResult:
    paper: Paper
    keyword_set_results: list[KeywordSetResult]

    @property
    def evaluated_count(self) -> int:
        return sum(r.evaluated_count for r in self.keyword_set_results)

    @property
    def passing_scholars(self) -> list[tuple[Scholar, float]]:
        """Flattened (scholar, score) pairs across every keyword set, for
        callers that just want "everything that passed" without caring
        which angle found it.
        """
        return [pair for r in self.keyword_set_results for pair in r.passing_scholars]


def run_search(
    *,
    title: str,
    abstract: str | None,
    keywords: list[str],
    db_path: Path,
    openalex_client: OpenAlexClient,
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.1",
    s2_client: SemanticScholarClient | None = None,
    staleness_months: int = 6,
    max_openalex_pages: int = 2,
    results_per_set: int = 5,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> SearchResult:
    """Runs the full search pipeline.

    The paper's title/abstract/keywords are first decomposed by a local
    Ollama model into 5 distinct 3-keyword search angles
    (discovery/keyword_summarizer.py), then each angle is searched
    independently end-to-end (discovery -> enrichment -> eligibility
    filtering -> email hunting -> ranking), keeping its own top
    `results_per_set` passing scholars. Eligibility rules stay 100%
    deterministic throughout -- the LLM only shapes what gets searched
    for, it never decides who passes.

    `on_progress`, if given, is called as `on_progress(stage, done, total)`.
    `stage` is either "generating_keywords" (once, up front) or
    "set_<N>_<phase>" where phase is one of "discovering", "enriching",
    "filtering", "email_hunt", "ranking" for N in 1..5, followed by a
    final "done".
    """

    def report(stage: str, done: int, total: int) -> None:
        if on_progress is not None:
            on_progress(stage, done, total)

    paper_repo = PaperRepository(db_path)
    keyword_set_repo = KeywordSetRepository(db_path)
    scholar_repo = ScholarRepository(db_path, staleness_months=staleness_months)
    match_repo = MatchRepository(db_path)

    paper = paper_repo.create(
        Paper(title=title, abstract=abstract, keywords=keywords, run_date=date.today())
    )

    report("generating_keywords", 0, 0)
    keyword_sets = generate_keyword_sets(paper, base_url=ollama_base_url, model=ollama_model)
    for ks in keyword_sets:
        ks.paper_id = paper.id
        keyword_set_repo.create(ks)
    report("generating_keywords", 1, 1)
    logger.info(
        "Decomposed paper %d into %d keyword sets: %s",
        paper.id,
        len(keyword_sets),
        ", ".join(f"[{ks.label}: {'/'.join(ks.keywords)}]" for ks in keyword_sets),
    )

    keyword_set_results: list[KeywordSetResult] = []
    for ks in keyword_sets:
        def sub_report(stage: str, done: int, total: int, _n: int = ks.set_index) -> None:
            report(f"set_{_n}_{stage}", done, total)

        result = _run_for_keyword_set(
            paper=paper,
            keyword_set=ks,
            scholar_repo=scholar_repo,
            match_repo=match_repo,
            openalex_client=openalex_client,
            s2_client=s2_client,
            max_openalex_pages=max_openalex_pages,
            results_per_set=results_per_set,
            report=sub_report,
        )
        keyword_set_results.append(result)

    report("done", 1, 1)
    return SearchResult(paper=paper, keyword_set_results=keyword_set_results)


def _run_for_keyword_set(
    *,
    paper: Paper,
    keyword_set: KeywordSet,
    scholar_repo: ScholarRepository,
    match_repo: MatchRepository,
    openalex_client: OpenAlexClient,
    s2_client: SemanticScholarClient | None,
    max_openalex_pages: int,
    results_per_set: int,
    report: Callable[[str, int, int], None],
) -> KeywordSetResult:
    # A throwaway Paper-shaped object carrying this set's own 3 keywords,
    # used only to build the search query / relevance ranking for this
    # angle -- matches/scholars are still persisted against the real paper.
    query_paper = Paper(
        id=paper.id,
        title=paper.title,
        abstract=paper.abstract,
        keywords=keyword_set.keywords,
        run_date=paper.run_date,
    )

    report("discovering", 0, 0)
    candidate_ids = find_candidate_openalex_author_ids(
        query_paper, openalex_client, max_pages=max_openalex_pages
    )
    logger.info(
        "Keyword set %d (%s): found %d candidate authors",
        keyword_set.set_index,
        keyword_set.label,
        len(candidate_ids),
    )

    scholars: list[Scholar] = []
    for i, author_id in enumerate(candidate_ids):
        report("enriching", i, len(candidate_ids))
        existing = scholar_repo.get(author_id)
        if existing and not scholar_repo.is_stale(existing):
            scholars.append(existing)
            continue

        try:
            raw_author = openalex_client.get_author(author_id)
            if raw_author is None:
                continue

            scholar, affiliation_history = scholar_from_openalex_author(raw_author, paper.run_date)
            scholar = carry_over_email(scholar, existing)
            if s2_client:
                try:
                    scholar = cross_check_with_semantic_scholar(scholar, s2_client)
                except Exception:
                    logger.warning(
                        "Semantic Scholar cross-check failed for %s", scholar.display_name, exc_info=True
                    )

            scholar_repo.upsert(scholar)
            scholar_repo.replace_affiliation_history(scholar.id, affiliation_history)
            scholars.append(scholar)
        except Exception:
            # One bad candidate (malformed data, an unexpected DB conflict,
            # a network fluke) must not sink an entire multi-minute search
            # that's already enriched dozens of other candidates -- skip it,
            # log it, and keep going.
            logger.warning("Skipping candidate author %s due to an unexpected error", author_id, exc_info=True)
            continue

    report("enriching", len(candidate_ids), len(candidate_ids))
    evaluated_count = len(scholars)

    # Core-rule pass (zone/institution/pubs/h-index) -- these never depend on
    # email, so candidates that fail here are recorded and dropped before
    # spending any scrape effort on them.
    report("filtering", 0, len(scholars))
    core_passing: list[Scholar] = []
    for scholar in scholars:
        passed, fail_reasons = passes_all_hard_rules(scholar, check_email=False)
        if passed:
            core_passing.append(scholar)
        else:
            match_repo.record_match(
                paper_id=paper.id,
                keyword_set_id=keyword_set.id,
                scholar_id=scholar.id,
                relevance_score=0.0,
                passed_hard_rules=False,
                fail_reasons=fail_reasons,
                rank_position=None,
            )
    report("filtering", len(scholars), len(scholars))

    # Email hunt: only for core-rule passers. Skip scholars that already
    # have an email (or a confirmed "not found") from a prior run.
    report("email_hunt", 0, len(core_passing))
    for i, scholar in enumerate(core_passing):
        if scholar.email_verification_status == EmailVerificationStatus.NOT_FOUND:
            try:
                hunt_email(scholar, openalex_client, session=openalex_client.session)
                scholar_repo.upsert(scholar)
            except Exception:
                # Same rationale as the enrichment loop above: a network
                # fluke (e.g. an OpenAlex 504) while hunting one scholar's
                # email must not sink an entire multi-minute search that's
                # already found and filtered dozens of other candidates.
                logger.warning(
                    "Skipping email hunt for %s due to an unexpected error", scholar.display_name, exc_info=True
                )
        report("email_hunt", i + 1, len(core_passing))

    # Final pass: now that email data is populated, actually enforce the
    # "must have a discovered email" rule.
    report("ranking", 0, len(core_passing))
    passing: list[Scholar] = []
    for scholar in core_passing:
        passed, fail_reasons = passes_all_hard_rules(scholar, check_email=True)
        if passed:
            passing.append(scholar)
        else:
            match_repo.record_match(
                paper_id=paper.id,
                keyword_set_id=keyword_set.id,
                scholar_id=scholar.id,
                relevance_score=0.0,
                passed_hard_rules=False,
                fail_reasons=fail_reasons,
                rank_position=None,
            )

    # Every passing scholar is ranked and persisted (full audit trail, same
    # philosophy as everywhere else in this project) -- only the returned
    # value is capped to results_per_set for display.
    ranked = rank_scholars(query_paper, passing)
    for position, (scholar, score) in enumerate(ranked, start=1):
        match_repo.record_match(
            paper_id=paper.id,
            keyword_set_id=keyword_set.id,
            scholar_id=scholar.id,
            relevance_score=score,
            passed_hard_rules=True,
            fail_reasons=[],
            rank_position=position,
        )
    report("ranking", len(core_passing), len(core_passing))

    top_n = ranked[:results_per_set]
    if len(top_n) < results_per_set:
        logger.warning(
            "Keyword set %d (%s): only %d of the requested %d scholars passed all hard rules.",
            keyword_set.set_index,
            keyword_set.label,
            len(top_n),
            results_per_set,
        )

    return KeywordSetResult(keyword_set=keyword_set, passing_scholars=top_n, evaluated_count=evaluated_count)
