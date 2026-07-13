from __future__ import annotations

import requests

BASE_URL = "https://api.semanticscholar.org/graph/v1"

AUTHOR_FIELDS = "name,externalIds,affiliations,homepage,paperCount,citationCount,hIndex,papers.year"


class SemanticScholarClient:
    """Thin client over the Semantic Scholar Graph API.

    Used as a secondary source to cross-check OpenAlex's h-index/paper-count
    and to source `homepage` URLs as email-hunting leads. Semantic Scholar
    has no institution country/type data, so it cannot drive zone/employer
    filtering on its own.
    """

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key} if self.api_key else {}

    def search_papers(self, query: str, limit: int = 50) -> list[dict]:
        """Search papers by topical relevance; each result has `authors[].authorId`."""
        resp = self.session.get(
            f"{BASE_URL}/paper/search",
            params={"query": query, "limit": limit, "fields": "authors"},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_author(self, author_id: str) -> dict | None:
        resp = self.session.get(
            f"{BASE_URL}/author/{author_id}",
            params={"fields": AUTHOR_FIELDS},
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def search_author_by_name(self, name: str) -> list[dict]:
        resp = self.session.get(
            f"{BASE_URL}/author/search",
            params={"query": name, "fields": AUTHOR_FIELDS},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


def extract_author_ids(papers: list[dict]) -> set[str]:
    ids: set[str] = set()
    for paper in papers:
        for author in paper.get("authors", []):
            author_id = author.get("authorId")
            if author_id:
                ids.add(author_id)
    return ids
