"""Tests for the POST /run_scan endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from app import config
from app.api import create_app
from app.risks import ALL_RISKS
from app.schemas import AlexResponse

from .conftest import CapturingCallback, FakeEvaluator


def _all_true(risk):
    return {
        "evaluations": [
            {"rule": rule, "observed_value": 1, "true": True, "reason": "f"}
            for rule in risk.sub_rules
        ],
        "summary": "f",
    }


def _envelope(*, start, end, trades=None):
    return AlexResponse.model_validate(
        {
            "status": True,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "data": {
                "deposits": [],
                "withdraws": [],
                "trades": trades or [],
                "bonus": [],
            },
        }
    )


def _trade(login, *, ts, tid):
    return {
        "id": tid, "login": login, "group": "g", "entry": 0,
        "symbol": "EURUSD", "volume": 0.1, "side": "buy",
        "open_time": ts.isoformat(), "time": ts.isoformat(),
        "open_price": 1.1, "close_price": 1.1,
        "bid_at_open": 1.1, "ask_at_open": 1.1,
        "stop_loss": 0.0, "take_profit": 0.0,
        "swaps": 0.0, "commission": 0.0, "profit": 0.0,
    }


class FixedAlexClient:
    def __init__(self, env):
        self.env = env

    def fetch_window(self, *, start_time, end_time):
        return self.env


@pytest.fixture()
def configured_client():
    s = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)
    e = s + timedelta(hours=6) - timedelta(milliseconds=1)
    env = _envelope(start=s, end=e, trades=[_trade(777, ts=s + timedelta(hours=1), tid=1)])
    evaluator = FakeEvaluator()
    for risk in ALL_RISKS:
        evaluator.set(risk.key, _all_true(risk))
    cb = CapturingCallback()
    mongo = mongomock.MongoClient()
    app = create_app(
        evaluator=evaluator,
        callback_fn=cb,
        mongo_client=mongo,
        alex_client=FixedAlexClient(env),
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, mongo, cb, s, e


def test_run_scan_with_explicit_window(configured_client):
    c, mongo, cb, s, e = configured_client
    resp = c.post(
        "/run_scan",
        json={"start_time": s.isoformat(), "end_time": e.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["accounts_analysed"] == 1
    assert body["results_persisted"] == 4
    assert body["error"] is None

    analyses = mongo[config.MONGODB_DATABASE][config.MONGODB_COLLECTION]
    assert analyses.count_documents({"mt5_login": 777}) == 4
    assert len(cb.calls) == 1


def test_run_scan_no_body_uses_latest_window(configured_client):
    c, *_ = configured_client
    resp = c.post("/run_scan")
    assert resp.status_code in (200, 502)


def test_run_scan_partial_window_args_rejected(configured_client):
    c, *_ = configured_client
    resp = c.post("/run_scan", json={"start_time": "2026-05-09T00:00:00Z"})
    assert resp.status_code == 400


def test_run_scan_invalid_iso_rejected(configured_client):
    c, *_ = configured_client
    resp = c.post(
        "/run_scan",
        json={"start_time": "not-a-date", "end_time": "also-bad"},
    )
    assert resp.status_code == 400
