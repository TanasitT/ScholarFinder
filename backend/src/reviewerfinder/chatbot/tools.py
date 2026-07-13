from __future__ import annotations

from datetime import date
from pathlib import Path

from langchain_core.tools import BaseTool, tool
from rapidfuzz import process

from config.settings import settings
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.db.repository import MatchRepository, PaperRepository, ScholarRepository
from reviewerfinder.discovery.enrichment import carry_over_email, scholar_from_openalex_author
from reviewerfinder.models import Scholar
from reviewerfinder.pipeline import run_search
from reviewerfinder.rules.filters import passes_all_hard_rules
from reviewerfinder.rules.ranking import relevance_score

FUZZY_NAME_SCORE_CUTOFF = 70


def _fuzzy_find_scholar(scholar_repo: ScholarRepository, query: str) -> Scholar | None:
    scholars = scholar_repo.list_all()
    if not scholars:
        return None
    choices = {s.id: s.display_name for s in scholars}
    match = process.extractOne(query, choices, score_cutoff=FUZZY_NAME_SCORE_CUTOFF)
    if not match:
        return None
    _matched_name, _score, matched_id = match
    return next((s for s in scholars if s.id == matched_id), None)


def build_tools(
    db_path: Path, openalex_client: OpenAlexClient, staleness_months: int = 6
) -> list[BaseTool]:
    """Build the chatbot's tool set, closing over db_path/openalex_client so
    the tools are testable with a tmp DB and a fake client rather than
    relying on module-level global state.
    """
    paper_repo = PaperRepository(db_path)
    scholar_repo = ScholarRepository(db_path, staleness_months=staleness_months)
    match_repo = MatchRepository(db_path)

    @tool
    def lookup_scholar(name_or_id: str) -> dict:
        """Look up a stored scholar by their exact OpenAlex ID or by (fuzzy) display name.

        Returns their profile: institution, country zone, h-index, recent-paper
        count, email/verification status, and research topics. Returns
        {"error": ...} if nothing matches -- report that plainly rather than
        guessing who the user meant.
        """
        scholar = scholar_repo.get(name_or_id)
        if not scholar:
            scholar = _fuzzy_find_scholar(scholar_repo, name_or_id)
        if not scholar:
            return {"error": f"No stored scholar matches '{name_or_id}'."}
        return scholar.model_dump(mode="json")

    @tool
    def lookup_paper(title_or_id: str) -> dict:
        """Look up a stored paper by its numeric ID or by its exact title.

        Returns title/abstract/keywords/run_date. Returns {"error": ...} if
        nothing matches.
        """
        paper = None
        if title_or_id.strip().isdigit():
            paper = paper_repo.get(int(title_or_id))
        if not paper:
            paper = paper_repo.find_by_title(title_or_id)
        if not paper:
            return {"error": f"No stored paper matches '{title_or_id}'."}
        return paper.model_dump(mode="json")

    @tool
    def check_scholar_fit(scholar_id: str, paper_id: int) -> dict:
        """Definitively check whether a stored scholar is eligible to review a stored paper.

        Re-runs all hard eligibility rules live (country zone, academic
        institution, 8+ recent papers, h-index threshold, discovered email),
        refreshing the scholar's data from OpenAlex first if it's stale.
        ALWAYS report this tool's `passed` and `fail_reasons` verbatim --
        never assert a scholar is or isn't eligible from your own judgment,
        only from this tool's result.
        """
        scholar = scholar_repo.get(scholar_id)
        if not scholar:
            return {"error": f"No stored scholar with id '{scholar_id}'."}
        paper = paper_repo.get(paper_id)
        if not paper:
            return {"error": f"No stored paper with id {paper_id}."}

        if scholar_repo.is_stale(scholar) and scholar.openalex_id:
            raw_author = openalex_client.get_author(scholar.openalex_id)
            if raw_author is not None:
                refreshed, history = scholar_from_openalex_author(raw_author, date.today())
                scholar = carry_over_email(refreshed, scholar)
                scholar_repo.upsert(scholar)
                scholar_repo.replace_affiliation_history(scholar.id, history)

        passed, fail_reasons = passes_all_hard_rules(scholar, check_email=True)
        score = relevance_score(paper, scholar)
        return {
            "scholar_id": scholar.id,
            "paper_id": paper.id,
            "passed": passed,
            "fail_reasons": fail_reasons,
            "relevance_score": score,
        }

    @tool
    def list_top_candidates(paper_id: int, limit: int = 10) -> list[dict]:
        """List the top-ranked scholars that already passed all hard rules for a stored paper.

        Most relevant first. Returns an empty list if no search has been run
        for this paper yet (tell the user that, don't assume it means zero
        eligible scholars exist).
        """
        rows = match_repo.top_candidates(paper_id, limit=limit)
        return [dict(row) for row in rows]

    @tool
    def search_new_candidates(paper_id: int) -> dict:
        """Re-run the full discovery pipeline for an already-stored paper to find candidate scholars.

        This decomposes the paper into 5 distinct keyword-set angles (via a
        local Ollama model) and searches each independently, then calls
        external APIs and spends OpenAlex's daily credit budget -- only
        call this after the user has explicitly confirmed in this
        conversation that they want to spend that budget. Note this
        creates a NEW paper record (a fresh dated search run, same as the
        existing schema does for repeated searches) rather than mutating
        paper_id -- report the new paper_id back to the user.
        """
        paper = paper_repo.get(paper_id)
        if not paper:
            return {"error": f"No stored paper with id {paper_id}."}

        result = run_search(
            title=paper.title,
            abstract=paper.abstract,
            keywords=paper.keywords,
            db_path=db_path,
            openalex_client=openalex_client,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            s2_client=None,
            staleness_months=staleness_months,
        )
        return {
            "new_paper_id": result.paper.id,
            "evaluated_count": result.evaluated_count,
            "passing_count": len(result.passing_scholars),
            "keyword_sets": [
                {
                    "label": sr.keyword_set.label,
                    "keywords": sr.keyword_set.keywords,
                    "scholar_ids": [s.id for s, _ in sr.passing_scholars],
                }
                for sr in result.keyword_set_results
            ],
        }

    return [
        lookup_scholar,
        lookup_paper,
        check_scholar_fit,
        list_top_candidates,
        search_new_candidates,
    ]
