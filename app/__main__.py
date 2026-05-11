"""Console entrypoint: `uv run app` boots uvicorn against `app.main:app`."""

from __future__ import annotations

import os

import uvicorn

from .logging_config import configure_logging


def main() -> None:
    configure_logging()
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5050")),
        reload=os.getenv("RELOAD", "false").lower() in {"1", "true", "yes"},
        log_config=None,
    )


if __name__ == "__main__":
    main()
