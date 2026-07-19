from __future__ import annotations

from reviewerfinder.clients import openalex as openalex_mod
from reviewerfinder.clients import semantic_scholar as s2_mod
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.models import Paper


def build_search_query(paper: Paper) -> str:
    """Builds a full-text/semantic search query from a paper's keywords
    only -- never the title or abstract. Each keyword-set angle is meant to
    search narrowly on its own 3 keywords (see pipeline.py); folding in the
    full abstract dilutes that signal identically for every set, and a long
    or PDF-copy-pasted abstract (with hard-wrap hyphenation artifacts
    splitting words like "inexpen-sive") used to be able to break OpenAlex's
    old boolean `search` matching outright. Falls back to the title if a
    paper has no keywords at all (shouldn't happen for a keyword-set's own
    3 keywords in practice).
    """
    if paper.keywords:
        return " ".join(paper.keywords)
    return paper.title


def find_candidate_openalex_author_ids(
    paper: Paper, client: OpenAlexClient, max_pages: int = 2
) -> set[str]:
    """Uses OpenAlex's embeddings-based `search.semantic` (via
    `search_works_semantic`) rather than its literal-term `search` --
    confirmed live that the latter's default boolean-AND-like matching
    returned 0 candidates the moment a paper's own rare/novel term was in
    the query, while semantic search returned dozens of genuinely on-topic
    results for the same text.
    """
    query = build_search_query(paper)
    works = client.search_works_semantic(query, max_pages=max_pages)
    return openalex_mod.extract_author_ids(works)


def find_candidate_semantic_scholar_author_ids(
    paper: Paper, client: SemanticScholarClient, limit: int = 50
) -> set[str]:
    query = build_search_query(paper)
    papers = client.search_papers(query, limit=limit)
    return s2_mod.extract_author_ids(papers)
