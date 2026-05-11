"""Centralised logging setup.

Configure once at process startup via `configure_logging()`. Tests do
not call this — they use pytest's default capture so logs surface only
on failure.

Format is single-line key=value so logs grep cleanly in production
(`grep mt5_login=70001 app.log`) and stay readable in dev.
"""

from __future__ import annotations

import logging
import os
import sys


_DEFAULT_FORMAT = (
    "%(asctime)s %(levelname)-5s %(name)s :: %(message)s"
)


def configure_logging(level: str | None = None) -> None:
    """Idempotent root logger setup. Honours `LOG_LEVEL` env var."""
    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger()

    # Replace existing handlers so re-running (e.g. uvicorn --reload) doesn't
    # duplicate log lines.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    root.addHandler(handler)
    root.setLevel(resolved)

    # Quiet down noisy libraries — keep WARNING+ for httpx access logs etc.
    for noisy in ("httpx", "httpcore", "tortoise", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
