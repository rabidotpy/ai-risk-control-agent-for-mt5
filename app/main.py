"""FastAPI application factory.

Run locally with::

    uvicorn app.main:app --reload --port 5050

Tortoise is initialised on lifespan startup. Tests build their own app
via `create_app(...)` and inject a fake evaluator + callback by writing
to `app.state` directly.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

from fastapi import FastAPI
from tortoise.contrib.fastapi import RegisterTortoise

from .api import router
from .db import TORTOISE_ORM
from .llm import LLMEvaluator
from .logging_config import configure_logging


logger = logging.getLogger(__name__)


CallbackFn = Callable[[list[dict]], Awaitable[dict]]


def create_app(
    *,
    evaluator: LLMEvaluator | None = None,
    callback_fn: CallbackFn | None = None,
    init_database: bool = True,
) -> FastAPI:
    """Build the FastAPI app. Tests pass `init_database=False` and call
    `init_db()` themselves with a session-scoped fixture.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not init_database:
            logger.info("lifespan: skipping DB init (test mode)")
            yield
            return
        logger.info("lifespan: initialising Tortoise")
        async with RegisterTortoise(
            app,
            config=TORTOISE_ORM,
            generate_schemas=True,
            add_exception_handlers=False,
            _enable_global_fallback=True,
        ):
            logger.info("lifespan: Tortoise ready")
            yield
            logger.info("lifespan: shutting down")

    app = FastAPI(
        title="AI Risk Control Agent for MT5",
        description=(
            "Risk-rule + LLM evaluator over MT5 broker snapshots. "
            "Each /analyse_risk call returns the per-risk verdict AND "
            "an updated rolling behaviour summary per (mt5_login, risk_type)."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )
    app.state.evaluator = evaluator
    app.state.callback_fn = callback_fn
    app.include_router(router)
    return app


# Module-level app for `uvicorn app.main:app`.
configure_logging()
app = create_app()
