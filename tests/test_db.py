"""Repository tests against mongomock — save, upsert-on-rerun, lookup."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pymongo.errors import DuplicateKeyError

from app.db import repo
from app.engine import analyse
from app.risks import ALL_RISKS

from .conftest import FakeEvaluator
from .fixtures import all_false, all_true, sample_snapshot


def _populate(collection, evaluator, response_factory=all_true):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, response_factory(risk))
    snap = sample_snapshot()
    results = analyse(snap, evaluator)
    repo.save_results(
        collection,
        mt5_login=snap.mt5_login,
        start_time=snap.start_time,
        end_time=snap.end_time,
        results=results,
    )
    return snap, results


def test_save_then_get_roundtrip(collection):
    evaluator = FakeEvaluator()
    snap, _ = _populate(collection, evaluator)

    rows = repo.get_results(
        collection, mt5_login=snap.mt5_login, start_time=snap.start_time
    )
    assert len(rows) == 4
    keys_stored = sorted(row["risk_type"] for row in rows)
    assert keys_stored == [
        "bonus_abuse",
        "latency_arbitrage",
        "scalping",
        "swap_arbitrage",
    ]
    # Each row carries its bookkeeping fields.
    for row in rows:
        assert row["mt5_login"] == snap.mt5_login
        # mongomock strips tz; start_time round-trips with the same wall-clock value
        stored = row["start_time"]
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        assert stored == snap.start_time
        assert "created_at" in row
        assert "_id" not in row


def test_get_results_returns_empty_when_no_match(collection):
    rows = repo.get_results(
        collection,
        mt5_login=999_999,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert rows == []


def test_has_results(collection):
    evaluator = FakeEvaluator()
    snap, _ = _populate(collection, evaluator)

    assert repo.has_results(
        collection, mt5_login=snap.mt5_login, start_time=snap.start_time
    )
    assert not repo.has_results(
        collection,
        mt5_login=snap.mt5_login,
        start_time=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )


def test_resave_overwrites_existing_rows(collection):
    """Per Rabi's spec: re-saving for the same key set replaces the rows in place."""

    evaluator = FakeEvaluator()
    snap, _ = _populate(collection, evaluator, response_factory=all_true)
    # All initial rows have risk_score 100 (all_true).
    initial_rows = list(collection.find({"mt5_login": snap.mt5_login}, {"_id": False}))
    assert all(r["risk_score"] == 100 for r in initial_rows)

    # Re-run with all-false canned responses → every row should now show score 0.
    _, _ = _populate(collection, evaluator, response_factory=all_false)
    overwritten = list(collection.find({"mt5_login": snap.mt5_login}, {"_id": False}))
    assert collection.count_documents({"mt5_login": snap.mt5_login}) == 4
    assert all(r["risk_score"] == 0 for r in overwritten)


def test_indexes_created_on_collection(collection):
    info = collection.index_information()
    names = set(info)
    assert "uniq_login_starttime_risktype" in names
    assert "by_risk_type" in names
    assert "by_login_starttime" in names


def test_unique_constraint_raises_on_direct_duplicate_insert(collection):
    """Sanity check: a direct insert_one with a duplicate key still raises."""

    evaluator = FakeEvaluator()
    _populate(collection, evaluator)

    with pytest.raises(DuplicateKeyError):
        collection.insert_one(
            {
                "mt5_login": 200001,
                "start_time": datetime(2026, 5, 8, 0, 0, tzinfo=timezone.utc),
                "risk_type": "latency_arbitrage",
                "risk_score": 0,
            }
        )
