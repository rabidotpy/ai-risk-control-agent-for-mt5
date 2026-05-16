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

from app.config import settings
from app.db import close_db, init_db
from app.llm import LLMEvaluator
from app.main import create_app
from app.risks import Risk
from app.services import JobQueue


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


@pytest.fixture(autouse=True)
def _disable_filters_by_default(monkeypatch):
    """Existing tests assume every (snapshot × risk) reaches the LLM and
    every finding is forwarded. Tests that exercise the prescreen or the
    high-risk filter override these via their own monkeypatch.
    """
    monkeypatch.setattr(settings, "prescreen_enabled", False)
    monkeypatch.setattr(settings, "callback_min_score", 0)


@pytest.fixture
def evaluator() -> FakeEvaluator:
    return FakeEvaluator()


@pytest.fixture
def callback_fn() -> CapturingCallback:
    return CapturingCallback()


@pytest_asyncio.fixture
async def app(evaluator, callback_fn, db):
    """FastAPI app wired with fakes. Lifespan does NOT re-init the DB.

    A real `JobQueue` is wired and started inline (httpx's ASGITransport
    does not trigger FastAPI lifespan events, so tests start the worker
    explicitly here).
    """
    queue = JobQueue(
        evaluator_provider=lambda: evaluator,
        callback_fn=callback_fn,
        concurrency=1,
        max_size=64,
    )
    await queue.start()
    try:
        yield create_app(
            evaluator=evaluator,
            callback_fn=callback_fn,
            init_database=False,
            job_queue=queue,
        )
    finally:
        await queue.stop()


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
    """Build a canned evaluator response.

    The `evaluations` echo field is kept so legacy fixtures keep
    validating, but the production service ignores it — the Python rule
    engine is the source of truth for `true` / score.
    """
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


# -- Trade builders -----------------------------------------------------------


def make_trade(
    *,
    trade_id: int,
    login: int = 70001,
    symbol: str = "EURUSD",
    side: str = "buy",
    open_time: str = "2026-05-08T01:00:00Z",
    close_time: str = "2026-05-08T01:00:10Z",
    open_price: float = 1.1,
    close_price: float = 1.1001,
    bid_at_open: float = 1.0999,
    ask_at_open: float = 1.1001,
    volume: float = 0.1,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    swaps: float = 0.0,
    commission: float = 0.0,
    profit: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": trade_id,
        "login": login,
        "group": "real\\group-test",
        "symbol": symbol,
        "volume": volume,
        "side": side,
        "open_time": open_time,
        "time": close_time,
        "open_price": open_price,
        "close_price": close_price,
        "bid_at_open": bid_at_open,
        "ask_at_open": ask_at_open,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "swaps": swaps,
        "commission": commission,
        "profit": profit,
    }


def make_short_trades(
    n: int,
    *,
    start_id: int = 1000,
    base_minute: int = 0,
    hold_seconds: int = 10,
    side: str = "buy",
    profit: float = 1.0,
) -> list[dict[str, Any]]:
    """Make N short-hold trades, one per minute, scattered close times."""
    trades = []
    for i in range(n):
        minute = base_minute + i
        hh, mm = divmod(minute, 60)
        open_time = f"2026-05-08T{1 + hh:02d}:{mm:02d}:00Z"
        sec = hold_seconds % 60
        extra_min = hold_seconds // 60
        close_mm = (mm + extra_min) % 60
        close_hh = 1 + hh + (mm + extra_min) // 60
        close_time = f"2026-05-08T{close_hh:02d}:{close_mm:02d}:{sec:02d}Z"
        trades.append(
            make_trade(
                trade_id=start_id + i,
                side=side,
                open_time=open_time,
                close_time=close_time,
                profit=profit,
            )
        )
    return trades
