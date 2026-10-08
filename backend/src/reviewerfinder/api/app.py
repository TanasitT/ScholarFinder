from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config.settings import DB_PATH, settings
from reviewerfinder.api.routes import papers, scholars
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.connection import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DB_PATH)
    # Browsing already-stored papers/scholars shouldn't require an OpenAlex
    # key -- only the /search endpoint needs it, and checks for None itself
    # (via api/deps.py::get_openalex_client) rather than failing app startup.
    app.state.openalex_client = (
        OpenAlexClient(api_key=settings.openalex_api_key, mailto=settings.openalex_mailto)
        if settings.openalex_api_key
        else None
    )
    app.state.semantic_scholar_client = SemanticScholarClient(
        api_key=settings.semantic_scholar_api_key
    )
    yield


app = FastAPI(title="ScholarFinder API", lifespan=lifespan)
app.include_router(papers.router)
app.include_router(scholars.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Without this, an unhandled exception returns a bare 500 with no
    response body at all -- the frontend's error handling expects a
    `{"detail": ...}` JSON body (same shape FastAPI's own HTTPException
    produces) and falls back to a generic, unhelpful message otherwise.
    The full traceback still goes to the server log via `logger.exception`;
    only the short message reaches the client. This is a local single-user
    dev tool with no auth, so surfacing the message is a reasonable
    debugging aid -- reconsider before reusing this as-is behind real auth.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
