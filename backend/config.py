from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    recall_api_key: str = ""
    recall_verification_secret: str = ""
    recall_region: str = "us-west-2"
    tavily_api_key: str = ""
    redis_url: str = "redis://localhost:6379"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    resend_api_key: str = ""
    email_from: str = "yaco@yourdomain.com"
    public_base_url: str = "http://localhost:8000"
    bot_name: str = "Yaco"
    speak_cooldown_secs: int = 90
    doc_relevance_threshold: float = 0.82
    idea_confirmation_window_secs: int = 20
    min_chunk_words: int = 15
    calendar_poll_interval_mins: int = 5
    transcripts_dir: Path = Path("./transcripts")

    @property
    def recall_base_url(self) -> str:
        return f"https://{self.recall_region}.recall.ai/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
