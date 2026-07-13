from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from config.settings import CHAT_SESSIONS_DB_PATH


def checkpointer_context(db_path: Path = CHAT_SESSIONS_DB_PATH):
    """Context manager yielding a SqliteSaver for chat conversation state.

    Deliberately a separate SQLite file from reviewerfinder.db's domain
    tables (papers/scholars/matches) -- conversation-turn history is not
    application data. Usage: `with checkpointer_context() as checkpointer:`.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver.from_conn_string(str(db_path))
