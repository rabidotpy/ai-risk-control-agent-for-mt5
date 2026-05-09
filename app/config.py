"""Environment-driven config.

Reads .env once at import time. Tests override via monkeypatch on the
attributes here, never by re-reading the env.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")
CLAUDE_MAX_TOKENS: int = int(os.getenv("CLAUDE_MAX_TOKENS", "1024"))

CALLBACK_URL: str = os.getenv("CALLBACK_URL", "")
CALLBACK_TIMEOUT_SECONDS: float = float(os.getenv("CALLBACK_TIMEOUT_SECONDS", "10"))

# MongoDB — persistence + GET /analyses lookup path.
MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "risk_control")
MONGODB_COLLECTION: str = os.getenv("MONGODB_COLLECTION", "risk_analyses")

# Phase B — raw broker pulls cached locally so we can aggregate windows
# longer than Alex's per-call slice (24h, 72h, 30d). TTL-indexed so the
# cache auto-expires; we are NOT a system of record for raw events.
RAW_PULLS_COLLECTION: str = os.getenv("RAW_PULLS_COLLECTION", "raw_pulls")
RAW_PULL_TTL_DAYS: int = int(os.getenv("RAW_PULL_TTL_DAYS", "35"))

# Phase B — Alex broker data feed.
# Stub mode (default) lets us run without a live broker endpoint by
# loading from tests/fixtures/alex_*.json. Flip ALEX_MODE=http and set
# ALEX_BASE_URL to switch to the real client.
ALEX_MODE: str = os.getenv("ALEX_MODE", "stub").lower()
ALEX_BASE_URL: str = os.getenv("ALEX_BASE_URL", "")
ALEX_API_KEY: str = os.getenv("ALEX_API_KEY", "")
ALEX_TIMEOUT_SECONDS: float = float(os.getenv("ALEX_TIMEOUT_SECONDS", "30"))
ALEX_STUB_FIXTURES_DIR: str = os.getenv(
    "ALEX_STUB_FIXTURES_DIR", "tests/fixtures"
)

# Phase B — APScheduler. Disabled by default so importing the app for tests
# or one-shot CLI use never spawns a background thread. The production
# entrypoint (`python -m app.jobs.scheduler`) flips it on.
SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
# Cron expression for the scan job — defaults to PRD §5 cadence (4×/day UTC).
SCHEDULER_HOURS: str = os.getenv("SCHEDULER_HOURS", "0,6,12,18")


def is_test_mode() -> bool:
    return os.getenv("APP_ENV", "").lower() == "test" or os.getenv("PYTEST_CURRENT_TEST") is not None
