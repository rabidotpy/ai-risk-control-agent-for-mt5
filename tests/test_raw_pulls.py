"""Tests for app/db/raw_pulls.py — TTL cache for the 6h Alex envelopes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock

from app.db import raw_pulls
from app.schemas import AlexResponse


def _envelope(*, start: datetime, end: datetime, trades=None, deposits=None) -> AlexResponse:
    return AlexResponse.model_validate(
        {
            "status": True,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "data": {
                "deposits": deposits or [],
                "withdraws": [],
                "trades": trades or [],
                "bonus": [],
            },
        }
    )


def _trade(login: int, *, ts: datetime, tid: int = 1) -> dict:
    return {
        "id": tid,
        "login": login,
        "group": "real\\g",
        "entry": 0,
        "symbol": "EURUSD",
        "volume": 0.1,
        "side": "buy",
        "open_time": ts.isoformat(),
        "time": ts.isoformat(),
        "open_price": 1.1,
        "close_price": 1.1,
        "bid_at_open": 1.1,
        "ask_at_open": 1.1,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "swaps": 0.0,
        "commission": 0.0,
        "profit": 0.0,
    }


def test_save_pull_extracts_logins_and_upserts_idempotently():
    coll = mongomock.MongoClient()["db"]["raw_pulls"]
    raw_pulls.ensure_indexes(coll)
    s = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)
    e = s + timedelta(hours=6) - timedelta(milliseconds=1)
    env = _envelope(start=s, end=e, trades=[_trade(111, ts=s + timedelta(hours=1))])

    raw_pulls.save_pull(coll, envelope=env)
    raw_pulls.save_pull(coll, envelope=env)  # idempotent (same window)

    docs = list(coll.find({}, projection={"_id": False}))
    assert len(docs) == 1
    assert docs[0]["logins"] == [111]
    # mongomock strips tzinfo — compare on the naive value.
    assert docs[0]["start_time"].replace(tzinfo=timezone.utc) == s
    assert docs[0]["end_time"].replace(tzinfo=timezone.utc) == e


def test_fetch_pulls_in_range_returns_only_overlapping_windows():
    coll = mongomock.MongoClient()["db"]["raw_pulls"]
    raw_pulls.ensure_indexes(coll)
    base = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)

    # Save 4 sequential 6h pulls.
    for i in range(4):
        s = base + timedelta(hours=6 * i)
        e = s + timedelta(hours=6) - timedelta(milliseconds=1)
        raw_pulls.save_pull(
            coll,
            envelope=_envelope(start=s, end=e, trades=[_trade(42, ts=s, tid=i)]),
        )

    # Range covering only the 2nd and 3rd pulls.
    range_start = base + timedelta(hours=6)
    range_end = base + timedelta(hours=18)
    matches = raw_pulls.fetch_pulls_in_range(
        coll, range_start=range_start, range_end=range_end
    )
    assert len(matches) == 3  # 2nd, 3rd, AND 4th pull (overlap touches it)


def test_fetch_pulls_filters_by_login():
    coll = mongomock.MongoClient()["db"]["raw_pulls"]
    raw_pulls.ensure_indexes(coll)
    s = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)
    e = s + timedelta(hours=6) - timedelta(milliseconds=1)
    raw_pulls.save_pull(
        coll,
        envelope=_envelope(start=s, end=e, trades=[_trade(111, ts=s)]),
    )
    raw_pulls.save_pull(
        coll,
        envelope=_envelope(
            start=s + timedelta(hours=6),
            end=e + timedelta(hours=6),
            trades=[_trade(222, ts=s + timedelta(hours=6))],
        ),
    )

    only_111 = raw_pulls.fetch_pulls_in_range(
        coll,
        range_start=s,
        range_end=s + timedelta(hours=12),
        login=111,
    )
    assert len(only_111) == 1
    assert only_111[0]["logins"] == [111]
