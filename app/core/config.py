from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DataPilot"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    agent_runtime: Literal["legacy", "langgraph"] = "legacy"
    database_url: str = "sqlite:///./data/datapilot.db"
    audit_database_url: str = "sqlite:///./data/audit.db"
    checkpoint_database_path: str = "./data/checkpoints.db"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 800
    llm_use_response_format: bool = False
    llm_trust_env: bool = False
    llm_enable_thinking: bool | None = None
    llm_max_retries: int = 1
    llm_retry_delay_seconds: float = 1.0
    query_max_rows: int = 200
    query_timeout_seconds: float = 5.0
    query_allowed_tables: str = (
        "regions,customers,categories,products,orders,order_items"
    )
    query_denied_columns: str = ""
    query_require_confirmation_for_high_risk: bool = True
    query_max_repair_attempts: int = 1
    query_enable_sql_review: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
