"""Test fixtures: a fake LLM evaluator + mongomock + Flask client wired to it."""

from __future__ import annotations

from typing import Any, Callable

import mongomock
import pytest

from app.api import create_app
from app.risks import Risk


class FakeEvaluator:
    """Drop-in for AnthropicEvaluator. Returns canned responses keyed by risk.key."""

    def __init__(self, responses_by_key: dict[str, dict] | None = None):
        self._responses = responses_by_key or {}
        self.calls: list[tuple[str, str]] = []  # (risk.key, payload_json)

    def set(self, key: str, response: dict) -> None:
        self._responses[key] = response

    def evaluate(self, risk: Risk, payload_json: str) -> dict[str, Any]:
        self.calls.append((risk.key, payload_json))
        if risk.key not in self._responses:
            raise AssertionError(
                f"FakeEvaluator has no canned response for risk '{risk.key}'. "
                f"Configured keys: {sorted(self._responses)}"
            )
        return self._responses[risk.key]


class CapturingCallback:
    """Drop-in for callback.deliver. Records every call instead of POSTing."""

    def __init__(self, status: dict | None = None):
        self.calls: list[dict] = []
        self._status = status or {"url": "fake://callback", "status": "delivered", "http_status": 200}

    def __call__(self, body: dict) -> dict:
        self.calls.append(body)
        return dict(self._status)


@pytest.fixture()
def evaluator() -> FakeEvaluator:
    return FakeEvaluator()


@pytest.fixture()
def callback_capture() -> CapturingCallback:
    return CapturingCallback()


@pytest.fixture()
def mongo():
    """Fresh mongomock client per test — no shared state across tests."""
    return mongomock.MongoClient()


@pytest.fixture()
def collection(mongo):
    """The configured collection on the mongomock client."""
    from app import config as app_config
    from app.db.client import ensure_indexes

    coll = mongo[app_config.MONGODB_DATABASE][app_config.MONGODB_COLLECTION]
    ensure_indexes(coll)
    return coll


@pytest.fixture()
def client(evaluator: FakeEvaluator, callback_capture: CapturingCallback, mongo):
    app = create_app(
        evaluator=evaluator,
        callback_fn=callback_capture,
        mongo_client=mongo,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
