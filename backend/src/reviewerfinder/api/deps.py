from __future__ import annotations

from pathlib import Path

import requests
from fastapi import Depends, HTTPException, Request

from config.settings import DB_PATH, settings
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.repository import (
    KeywordSetRepository,
    MatchRepository,
    PaperRepository,
    ScholarRepository,
)


def get_db_path() -> Path:
    """Overridable in tests (via app.dependency_overrides) so nothing ever
    touches the real database -- every route/repository dependency must go
    through this rather than importing DB_PATH directly.
    """
    return DB_PATH


def get_paper_repository(db_path: Path = Depends(get_db_path)) -> PaperRepository:
    return PaperRepository(db_path)


def get_keyword_set_repository(db_path: Path = Depends(get_db_path)) -> KeywordSetRepository:
    return KeywordSetRepository(db_path)


def get_scholar_repository(db_path: Path = Depends(get_db_path)) -> ScholarRepository:
    return ScholarRepository(db_path, staleness_months=settings.scholar_staleness_months)


def get_match_repository(db_path: Path = Depends(get_db_path)) -> MatchRepository:
    return MatchRepository(db_path)


def check_ollama_reachable() -> None:
    """Fails fast with a clear 503 before starting a search job, rather than
    starting one that's doomed to error out a few seconds later because
    Ollama isn't running. Not overridable via a returned value (there's no
    "client" object to inject, just a local HTTP server) -- tests instead
    override this whole dependency to a no-op.
    """
    try:
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail=f"Couldn't reach Ollama at {settings.ollama_base_url} -- it's required to "
            f"decompose a paper into keyword sets before searching. Start it and make sure "
            f"'{settings.ollama_model}' is pulled (`ollama pull {settings.ollama_model}`).",
        ) from e


def get_openalex_client(request: Request) -> OpenAlexClient:
    client = request.app.state.openalex_client
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="OPENALEX_API_KEY is not configured on the server -- browsing works, but search does not.",
        )
    return client


def get_semantic_scholar_client(request: Request) -> SemanticScholarClient:
    return request.app.state.semantic_scholar_client
