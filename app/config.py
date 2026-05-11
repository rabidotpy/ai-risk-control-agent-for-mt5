"""Environment-driven settings.

Loaded once at import time via pydantic-settings. Tests override individual
attributes by monkeypatching the module-level `settings` singleton, never
by re-reading the env.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime knobs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic ------------------------------------------------------------
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-4-7"
    claude_max_tokens: int = 1024

    # Callback -------------------------------------------------------------
    callback_url: str = ""
    callback_timeout_seconds: float = 10.0

    # Database -------------------------------------------------------------
    # Tortoise URL. SQLite in-memory for tests, Postgres in dev/prod.
    # Examples:
    #   sqlite://:memory:
    #   sqlite:///./risk_control.db
    #   postgres://user:pass@host:5432/risk_control
    database_url: str = "sqlite://:memory:"

    # History --------------------------------------------------------------
    # When False, every /analyse_risk call is treated as fresh — prior
    # `RiskHistorySummary` rows are NOT loaded into the prompt and are NOT
    # upserted. Per-request `include_history` overrides this default.
    include_history_default: bool = True


settings = Settings()
