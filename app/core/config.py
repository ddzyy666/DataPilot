from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DataPilot"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    database_url: str = "sqlite:///./data/datapilot.db"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 800
    llm_use_response_format: bool = False
    llm_trust_env: bool = False
    llm_enable_thinking: bool | None = None
    query_max_rows: int = 200
    query_max_repair_attempts: int = 1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
