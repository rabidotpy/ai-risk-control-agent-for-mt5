"""Test fixtures.

Each test gets:
  * a fresh SQLite-in-memory Tortoise DB (tables created and dropped per test
    via `initializer` / `finalizer`),
  * a `FakeEvaluator` whose canned response per risk-key the test seeds,
  * a `CapturingCallback` recording every callback body,
  * an `AsyncClient` from httpx that talks to a FastAPI app wired with
    those fakes — no network, no Anthropic, no Postgres.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.db import close_db, init_db
from app.llm import LLMEvaluator
from app.main import create_app
from app.risks import Risk


class FakeEvaluator:
    """Canned-response evaluator. Tests seed `responses[risk.key]`."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None):
        self.responses: dict[str, dict[str, Any]] = responses or {}
        self.calls: list[tuple[str, str]] = []  # (risk_key, payload_json)

    async def evaluate(self, risk: Risk, request_payload_json: str) -> dict[str, Any]:
        self.calls.append((risk.key, request_payload_json))
        if risk.key not in self.responses:
            raise AssertionError(
                f"FakeEvaluator: no canned response for risk '{risk.key}'"
            )
        return self.responses[risk.key]


class CapturingCallback:
    """Async callback that records every body it receives."""

    def __init__(self):
        self.calls: list[list[dict]] = []

    async def __call__(self, body: list[dict]) -> dict:
        self.calls.append(body)
        return {"url": "test://capture", "status": "delivered", "http_status": 200}


@pytest_asyncio.fixture
async def db():
    """Fresh SQLite-in-memory DB for each test."""
    await init_db(generate_schemas=True)
    try:
        yield
    finally:
        await Tortoise._drop_databases()
        await close_db()


@pytest.fixture
def evaluator() -> FakeEvaluator:
    return FakeEvaluator()


@pytest.fixture
def callback_fn() -> CapturingCallback:
    return CapturingCallback()


@pytest_asyncio.fixture
async def app(evaluator, callback_fn, db):
    """FastAPI app wired with fakes. Lifespan does NOT re-init the DB."""
    return create_app(
        evaluator=evaluator,
        callback_fn=callback_fn,
        init_database=False,
    )


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# -- Snapshot helpers ---------------------------------------------------------


def make_snapshot_payload(
    *,
    mt5_login: int = 70001,
    trades: list[dict] | None = None,
    deposits: list[dict] | None = None,
    withdraws: list[dict] | None = None,
    bonus: list[dict] | None = None,
    linked_accounts: list[dict] | None = None,
    start_time: str = "2026-05-08T00:00:00Z",
    end_time: str = "2026-05-08T05:59:59.999000Z",
    trigger_type: str = "manual_run",
) -> dict[str, Any]:
    return {
        "mt5_login": mt5_login,
        "trigger_type": trigger_type,
        "start_time": start_time,
        "end_time": end_time,
        "trades": trades or [],
        "deposits": deposits or [],
        "withdraws": withdraws or [],
        "bonus": bonus or [],
        "linked_accounts": linked_accounts or [],
    }


def canned_response(
    *,
    sub_rules: tuple[str, ...],
    true_rules: tuple[str, ...] = (),
    summary: str = "test summary",
    behavior_summary: dict | None = None,
) -> dict[str, Any]:
    """Build a canned evaluator response that fires `true_rules`."""
    return {
        "evaluations": [
            {
                "rule": rule,
                "observed_value": 1,
                "true": rule in true_rules,
                "reason": f"canned: {rule}",
            }
            for rule in sub_rules
        ],
        "summary": summary,
        "behavior_summary": behavior_summary or {"run_count": 1, "notes": "first run"},
    }
