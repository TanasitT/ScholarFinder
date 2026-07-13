from __future__ import annotations

from pathlib import Path

from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.checkpoint.base import BaseCheckpointSaver

from config.settings import settings
from reviewerfinder.chatbot.tools import build_tools
from reviewerfinder.clients.openalex import OpenAlexClient

SYSTEM_PROMPT = """You are the ReviewerFinder assistant. You answer questions about \
academic papers and candidate peer-review scholars that have already been \
stored by the ReviewerFinder pipeline, using your tools to read that data.

Hard rules you must follow:
- Eligibility is NEVER your own judgment call. For "is scholar X fit to review \
paper Y" (or any eligibility question), call check_scholar_fit and report its \
`passed` and `fail_reasons` fields verbatim. Do not soften, override, or guess \
at eligibility from a scholar's profile yourself.
- search_new_candidates spends OpenAlex's daily API credit budget. Before \
calling it, explicitly ask the user to confirm they want to run a new search, \
and only call it after they say yes in this conversation.
- If a tool returns {"error": ...}, report that plainly rather than guessing \
who or what the user meant.
"""


def build_chatbot(
    db_path: Path,
    openalex_client: OpenAlexClient,
    checkpointer: BaseCheckpointSaver,
    staleness_months: int = 6,
):
    """Build the compiled LangGraph chatbot agent, wiring the tools defined
    in chatbot/tools.py (which themselves call the same deterministic
    rules/filters.py functions the batch pipeline uses) to a local Ollama
    model -- same model/server `search` uses for keyword-set generation, so
    the whole project needs no paid API key anywhere.
    """
    model = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
    )
    tools = build_tools(db_path, openalex_client, staleness_months=staleness_months)
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
