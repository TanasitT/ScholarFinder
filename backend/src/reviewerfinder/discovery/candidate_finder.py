from __future__ import annotations

from reviewerfinder.clients import openalex as openalex_mod
from reviewerfinder.clients import semantic_scholar as s2_mod
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.models import Paper


def build_search_query(paper: Paper) -> str:
    parts = [paper.title]
    if paper.abstract:
        parts.append(paper.abstract)
    if paper.keywords:
        parts.append(" ".join(paper.keywords))
    return " ".join(parts)


def find_candidate_openalex_author_ids(
    paper: Paper, client: OpenAlexClient, max_pages: int = 2
) -> set[str]:
    query = build_search_query(paper)
    works = client.search_works(query, max_pages=max_pages)
    return openalex_mod.extract_author_ids(works)


def find_candidate_semantic_scholar_author_ids(
    paper: Paper, client: SemanticScholarClient, limit: int = 50
) -> set[str]:
    query = build_search_query(paper)
    papers = client.search_papers(query, limit=limit)
    return s2_mod.extract_author_ids(papers)
