"""Runtime settings. Every value is documented in .env.example at the repo root."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # server
    repeat_port: int = 8765
    repeat_db_path: Path = BACKEND_DIR / "repeat.db"
    repeat_log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"

    # demo
    repeat_demo_mode: bool = True
    repeat_seed_demo: bool = True

    # llm
    repeat_llm_provider: Literal["openai", "mock"] = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-2024-08-06"

    # jira
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str = "DEMO"
    jira_issue_type: str = "Bug"

    # slack
    slack_bot_token: str | None = None
    slack_channel: str = "product-updates"

    # gmail
    gmail_credentials_file: Path = BACKEND_DIR / "tokens" / "gmail_client.json"
    gmail_token_file: Path = BACKEND_DIR / "tokens" / "gmail_token.json"
    gmail_handled_label: str = "REPEAT/handled"

    # narration
    repeat_narration_enabled: bool = True

    @property
    def llm_is_live(self) -> bool:
        return self.repeat_llm_provider == "openai" and bool(self.openai_api_key)

    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
