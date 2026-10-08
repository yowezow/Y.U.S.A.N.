from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class Settings(BaseSettings):
    """Runtime settings loaded from the local environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL
    yusan_host: str = "127.0.0.1"
    yusan_port: int = 8765
    yusan_log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
