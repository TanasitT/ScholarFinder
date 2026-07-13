from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZONES_FILE = DATA_DIR / "seed" / "zones.yaml"
DB_PATH = DATA_DIR / "reviewerfinder.db"
CHAT_SESSIONS_DB_PATH = DATA_DIR / "chat_sessions.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openalex_api_key: str | None = None
    openalex_mailto: str | None = None
    openalex_daily_budget_warning: float = 1.00

    semantic_scholar_api_key: str | None = None

    # Powers both keyword-set generation for `search` and the `chat`
    # chatbot's model -- a local Ollama server, chosen so the whole project
    # needs no paid API key anywhere. Must be running (`ollama serve`,
    # usually started automatically by the Ollama app) with `ollama_model`
    # already pulled (`ollama pull llama3.1`).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    scholar_staleness_months: int = 6

    def require_openalex_key(self) -> str:
        if not self.openalex_api_key:
            raise RuntimeError(
                "OPENALEX_API_KEY is required for this command. "
                "Copy .env.example to .env and set it (see README for how to obtain a free key)."
            )
        return self.openalex_api_key


settings = Settings()
