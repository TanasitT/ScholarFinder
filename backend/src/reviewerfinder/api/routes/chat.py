from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends

from reviewerfinder.api.deps import get_chatbot_agent
from reviewerfinder.api.schemas import ChatMessageRequest, ChatMessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatMessageResponse)
def send_chat_message(
    body: ChatMessageRequest,
    agent=Depends(get_chatbot_agent),
) -> ChatMessageResponse:
    """One synchronous chat turn over HTTP, reusing the same LangGraph agent
    the CLI's `chat` command uses (chatbot/agent.py::build_chatbot). Unlike
    /api/papers/search, this is NOT backgrounded -- a local-Ollama chat
    reply is expected in single-digit seconds, not minutes, so a simple
    blocking POST is acceptable and much simpler than the job-polling
    pattern search needs.

    `session_id` is a per-conversation thread id: omit it on the first
    message and the server mints one (returned in the response for the
    client to echo back on subsequent turns). This is distinct from the
    CLI's own single fixed thread_id="cli" -- concurrent browser sessions
    each need their own independent conversation thread. Both read/write
    the same chat_sessions.db; LangGraph's SqliteSaver supports any number
    of distinct thread_ids in one store.
    """
    session_id = body.session_id or str(uuid.uuid4())
    thread_config = {"configurable": {"thread_id": session_id}}

    result = agent.invoke(
        {"messages": [{"role": "user", "content": body.message}]},
        config=thread_config,
    )
    reply = result["messages"][-1].content
    return ChatMessageResponse(session_id=session_id, reply=reply)
