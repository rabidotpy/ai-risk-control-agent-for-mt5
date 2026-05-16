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

    # Background worker ----------------------------------------------------
    # When a request sets `enqueue_and_callback=true`, /analyse_risk returns
    # 202 Accepted and N background workers process the queue. The result is
    # POSTed to `callback_url` when ready. 0 disables the worker entirely
    # (the enqueue path will reject with 503).
    job_worker_concurrency: int = 1
    # Max in-memory queue depth — backpressure to prevent unbounded growth.
    job_queue_max_size: int = 1000

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

    # High-risk filter -----------------------------------------------------
    # Accounts whose maximum per-risk score is below this threshold are
    # dropped from the /analyse_risk response and from the callback POST
    # to Alex. Stored `RiskEvaluation` rows are NEVER filtered — the audit
    # trail in /analyses always shows the full picture.
    callback_min_score: int = 60

    # Cheap deterministic gate that runs before the LLM. Risks whose
    # prescreen returns False are not sent to Claude; a synthetic
    # `risk_score=0` row is persisted instead so the audit trail stays
    # complete. Disable to force every risk through the LLM.
    prescreen_enabled: bool = True

    # Post-rule LLM gate ---------------------------------------------------
    # After the Python rule engine produces a deterministic score, the LLM
    # is called to write a narrative ONLY if the score reaches this
    # threshold. Below this, a templated one-line summary is used instead.
    # Saves Anthropic spend on the long tail of low-risk accounts and
    # matches the same cut-off used by callback_min_score so the system
    # behaves consistently: low scores stay silent end-to-end.
    llm_narrate_min_score: int = 60


settings = Settings()
