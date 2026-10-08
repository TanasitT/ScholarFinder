from __future__ import annotations

import logging
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config.settings import DB_PATH, settings
from reviewerfinder.api.routes import chat, papers, scholars
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.connection import init_db

# The chatbot needs the optional `chatbot` extra (LangChain/LangGraph). The
# README's keyless demo installs only `.[api]`, so a missing extra must not
# stop the API from starting -- search and browsing still work, and
# /api/chat answers 503 instead.
try:
    from reviewerfinder.chatbot.agent import build_chatbot
    from reviewerfinder.chatbot.session import checkpointer_context
except ImportError:
    build_chatbot = None
    checkpointer_context = None

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

    # The chatbot agent/checkpointer are built once for the app's lifetime
    # (not per-request) -- see api/deps.py::get_chatbot_agent. Same
    # None-if-unconfigured pattern as openalex_client above: chat's tools
    # need an OpenAlexClient too (e.g. check_scholar_fit's staleness
    # refresh), so chat is unavailable rather than app startup failing when
    # no OPENALEX_API_KEY is configured. The reason is kept for the 503.
    app.state.chat_agent = None
    app.state.chat_unavailable_reason = None
    with ExitStack() as stack:
        if build_chatbot is None:
            app.state.chat_unavailable_reason = (
                'Chat is unavailable -- the chatbot packages are not installed (pip install -e ".[chatbot]").'
            )
        elif app.state.openalex_client is None:
            app.state.chat_unavailable_reason = (
                "Chat is unavailable -- OPENALEX_API_KEY is not configured on the server."
            )
        else:
            checkpointer = stack.enter_context(checkpointer_context())
            app.state.chat_checkpointer = checkpointer
            app.state.chat_agent = build_chatbot(
                db_path=DB_PATH,
                openalex_client=app.state.openalex_client,
                checkpointer=checkpointer,
                staleness_months=settings.scholar_staleness_months,
            )
        yield


app = FastAPI(title="ScholarFinder API", lifespan=lifespan)
app.include_router(papers.router)
app.include_router(scholars.router)
app.include_router(chat.router)


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
