"""Tests for the Phase B scan job — pull → cache → analyse → persist → callback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from app import config
from app.db import raw_pulls
from app.jobs.scan_job import ScanResult, latest_completed_window, run_scan
from app.risks import ALL_RISKS
from app.schemas import AlexResponse

from .conftest import CapturingCallback, FakeEvaluator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _all_true_response(risk):
    return {
        "evaluations": [
            {"rule": rule, "observed_value": 1, "true": True, "reason": "fixture"}
            for rule in risk.sub_rules
        ],
        "summary": "fixture",
    }


def _fake_envelope(*, start, end, trades=None):
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
    """Returns one canned envelope, ignoring the requested window."""

    def __init__(self, envelope: AlexResponse):
        self.envelope = envelope
        self.calls: list[tuple] = []

    def fetch_window(self, *, start_time, end_time):
        self.calls.append((start_time, end_time))
        return self.envelope


class FailingAlexClient:
    def fetch_window(self, *, start_time, end_time):
        from app.ingest.alex_client import AlexFetchError
        raise AlexFetchError("boom")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_latest_completed_window_aligns_to_six_hour_boundary():
    now = datetime(2026, 5, 9, 13, 30, tzinfo=timezone.utc)  # mid 12-18 window
    s, e = latest_completed_window(now=now)
    # 12-18 window not yet closed → previous window (06-12).
    assert s == datetime(2026, 5, 9, 6, 0, tzinfo=timezone.utc)
    assert (e - s) == timedelta(hours=6) - timedelta(milliseconds=1)


def test_run_scan_happy_path_persists_caches_and_calls_back():
    mongo = mongomock.MongoClient()
    s = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)
    e = s + timedelta(hours=6) - timedelta(milliseconds=1)

    env = _fake_envelope(
        start=s, end=e,
        trades=[_trade(111, ts=s + timedelta(hours=1), tid=1)],
    )
    alex = FixedAlexClient(env)

    evaluator = FakeEvaluator()
    for risk in ALL_RISKS:
        evaluator.set(risk.key, _all_true_response(risk))

    cb = CapturingCallback()

    summary = run_scan(
        mongo_client=mongo,
        evaluator=evaluator,
        alex_client=alex,
        callback_fn=cb,
        start_time=s,
        end_time=e,
        deliver_callback_blocking=True,
    )

    assert isinstance(summary, ScanResult)
    assert summary.error is None
    assert summary.accounts_analysed == 1
    assert summary.accounts_failed == 0
    assert summary.results_persisted == 4

    # Raw pull cached.
    raw_docs = list(raw_pulls.get_collection(mongo).find({}, projection={"_id": False}))
    assert len(raw_docs) == 1
    assert raw_docs[0]["logins"] == [111]

    # risk_analyses persisted (4 rows for one login).
    analyses = mongo[config.MONGODB_DATABASE][config.MONGODB_COLLECTION]
    assert analyses.count_documents({"mt5_login": 111}) == 4

    # Callback got the full batch.
    assert len(cb.calls) == 1
    assert len(cb.calls[0]) == 4


def test_run_scan_short_circuits_on_alex_failure():
    mongo = mongomock.MongoClient()
    summary = run_scan(
        mongo_client=mongo,
        evaluator=FakeEvaluator(),
        alex_client=FailingAlexClient(),
        callback_fn=CapturingCallback(),
        start_time=datetime(2026, 5, 9, tzinfo=timezone.utc),
        end_time=datetime(2026, 5, 9, 6, tzinfo=timezone.utc),
        deliver_callback_blocking=True,
    )
    assert summary.error is not None
    assert summary.error.startswith("alex_fetch_failed")
    assert summary.accounts_analysed == 0


def test_run_scan_handles_empty_window_cleanly():
    mongo = mongomock.MongoClient()
    s = datetime(2026, 5, 9, tzinfo=timezone.utc)
    e = s + timedelta(hours=6) - timedelta(milliseconds=1)
    env = _fake_envelope(start=s, end=e, trades=[])

    summary = run_scan(
        mongo_client=mongo,
        evaluator=FakeEvaluator(),
        alex_client=FixedAlexClient(env),
        callback_fn=CapturingCallback(),
        start_time=s,
        end_time=e,
        deliver_callback_blocking=True,
    )
    assert summary.error is None
    assert summary.accounts_analysed == 0
    assert summary.accounts_failed == 0
