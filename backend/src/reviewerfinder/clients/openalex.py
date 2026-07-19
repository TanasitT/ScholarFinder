from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://api.openalex.org"


class OpenAlexClient:
    """Thin client over the OpenAlex API.

    As of Feb 2026 OpenAlex requires an API key and bills usage-based daily
    credits, so callers should keep `max_pages`/`per_page` bounded rather
    than paginating exhaustively.
    """

    def __init__(self, api_key: str, mailto: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key
        self.mailto = mailto
        self.session = session or requests.Session()

    def _params(self, **extra: Any) -> dict:
        params = {"api_key": self.api_key, **extra}
        if self.mailto:
            params["mailto"] = self.mailto
        return params

    def search_works(self, query: str, per_page: int = 25, max_pages: int = 2) -> list[dict]:
        """Search works by title/abstract/fulltext relevance to `query`.

        Returns raw OpenAlex work objects (each has `authorships[].author.id`).
        """
        works: list[dict] = []
        cursor = "*"
        for _ in range(max_pages):
            resp = self.session.get(
                f"{BASE_URL}/works",
                params=self._params(search=query, per_page=per_page, cursor=cursor),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            works.extend(data.get("results", []))
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
        return works

    def search_works_semantic(self, query: str, max_pages: int = 2) -> list[dict]:
        """Search works by embeddings-based semantic similarity to `query`
        (OpenAlex's `search.semantic` param) rather than literal term
        matching. Unlike `search_works`, this endpoint has no cursor
        pagination (`cursor=*` returns a 400) and caps `per_page` at 50 --
        it uses plain `page` numbering over a capped result pool instead.

        Robust to messy/novel free text in a way `search_works` isn't: a
        live search against a real paper's full title returned 0 results
        via `search_works` (its own rare, not-yet-indexed coined term
        crushed the relevance ranking when combined with any other term),
        while the identical text via `search.semantic` returned dozens of
        genuinely on-topic results.
        """
        per_page = 50
        works: list[dict] = []
        for page in range(1, max_pages + 1):
            resp = self.session.get(
                f"{BASE_URL}/works",
                params=self._params(**{"search.semantic": query}, per_page=per_page, page=page),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            works.extend(results)
            if len(results) < per_page:
                break
        return works

    def get_author_recent_works(self, author_id: str, limit: int = 5) -> list[dict]:
        """Fetch an author's most recent works, each carrying `open_access.oa_url`.

        Used by email_hunter.py to find an open-access landing page/PDF to
        scrape for a contact email.
        """
        resp = self.session.get(
            f"{BASE_URL}/works",
            params=self._params(
                filter=f"author.id:{author_id}",
                sort="publication_date:desc",
                per_page=limit,
                select="id,doi,open_access,publication_date",
            ),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    def get_author(self, author_id: str) -> dict | None:
        """Fetch a single Author object by OpenAlex ID (e.g. 'A123456789')."""
        resp = self.session.get(
            f"{BASE_URL}/authors/{author_id}",
            params=self._params(),
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


def extract_author_ids(works: list[dict]) -> set[str]:
    """Flatten a list of OpenAlex work objects into a unique set of author IDs."""
    ids: set[str] = set()
    for work in works:
        for authorship in work.get("authorships", []):
            author = authorship.get("author") or {}
            author_id = author.get("id")
            if author_id:
                # OpenAlex IDs come back as full URLs; normalize to the bare ID.
                ids.add(author_id.rsplit("/", 1)[-1])
    return ids
