"""Tests for app/history/aggregator.py — long-window counters + verdict trend."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock

from app import config
from app.db import raw_pulls
from app.history.aggregator import build_historical_context
from app.schemas import AlexResponse


LOGIN = 555


def _env(*, start, end, trades=None, bonus=None, withdraws=None):
    return AlexResponse.model_validate(
        {
            "status": True,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "data": {
                "deposits": [],
                "withdraws": withdraws or [],
                "trades": trades or [],
                "bonus": bonus or [],
            },
        }
    )


def _trade(*, tid, ts):
    return {
        "id": tid, "login": LOGIN, "group": "g", "entry": 0,
        "symbol": "EURUSD", "volume": 0.1, "side": "buy",
        "open_time": ts.isoformat(), "time": ts.isoformat(),
        "open_price": 1.1, "close_price": 1.1,
        "bid_at_open": 1.1, "ask_at_open": 1.1,
        "stop_loss": 0.0, "take_profit": 0.0,
        "swaps": 0.0, "commission": 0.0, "profit": 0.0,
    }


def _bonus(*, bid, ts):
    return {"id": bid, "login": LOGIN, "group": "g", "time": ts.isoformat(), "profit": 100.0}


def _withdraw(*, wid, ts):
    return {"id": wid, "login": LOGIN, "group": "g", "time": ts.isoformat(), "profit": -50.0}


def test_lookbacks_aggregate_across_24h_and_30d():
    mongo = mongomock.MongoClient()
    raw_coll = raw_pulls.get_collection(mongo)
    raw_pulls.ensure_indexes(raw_coll)

    end = datetime(2026, 5, 10, 0, 0, tzinfo=timezone.utc)
    # Four 6h pulls covering the last 24h, each with 5 trades.
    for i in range(4):
        s = end - timedelta(hours=6 * (i + 1))
        e = s + timedelta(hours=6) - timedelta(milliseconds=1)
        trades = [_trade(tid=i * 10 + j, ts=s + timedelta(minutes=j)) for j in range(5)]
        raw_pulls.save_pull(raw_coll, envelope=_env(start=s, end=e, trades=trades))

    ctx = build_historical_context(
        mongo_client=mongo,
        mt5_login=LOGIN,
        window_start=end - timedelta(hours=6),
        window_end=end,
        risk_keys=("scalping",),
    )
    assert ctx["lookbacks"]["trade_count_24h"] == 20
    assert ctx["lookbacks"]["trade_count_30d"] == 20
    assert ctx["lookbacks"]["raw_pulls_used"] == 4
    assert ctx["lookbacks"]["most_recent_bonus_time"] is None


def test_bonus_aftermath_metrics():
    mongo = mongomock.MongoClient()
    raw_coll = raw_pulls.get_collection(mongo)
    raw_pulls.ensure_indexes(raw_coll)

    end = datetime(2026, 5, 10, 0, 0, tzinfo=timezone.utc)
    bonus_t = end - timedelta(hours=12)
    s = end - timedelta(hours=18)
    e = end
    # Pull spans the bonus + a withdrawal 10h later.
    trades = [_trade(tid=1, ts=bonus_t + timedelta(minutes=30))]
    bonus_evt = _bonus(bid=999, ts=bonus_t)
    wd = _withdraw(wid=2, ts=bonus_t + timedelta(hours=10))
    raw_pulls.save_pull(
        raw_coll, envelope=_env(start=s, end=e, trades=trades, bonus=[bonus_evt], withdraws=[wd])
    )

    ctx = build_historical_context(
        mongo_client=mongo,
        mt5_login=LOGIN,
        window_start=end - timedelta(hours=6),
        window_end=end,
        risk_keys=("bonus_abuse",),
    )
    lk = ctx["lookbacks"]
    assert lk["bonus_count_30d"] == 1
    assert lk["trades_within_24h_after_bonus"] == 1
    assert lk["withdrawal_within_72h_of_bonus"] is True
    assert lk["hours_bonus_to_withdrawal"] == 10.0


def test_trend_block_reads_recent_verdicts():
    mongo = mongomock.MongoClient()
    raw_coll = raw_pulls.get_collection(mongo)
    raw_pulls.ensure_indexes(raw_coll)

    # Seed risk_analyses with 5 prior scalping verdicts.
    analyses = mongo[config.MONGODB_DATABASE][config.MONGODB_COLLECTION]
    base = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    for i, score in enumerate([20, 80, 90, 50, 100]):
        analyses.insert_one(
            {
                "mt5_login": LOGIN,
                "risk_type": "scalping",
                "risk_score": score,
                "risk_level": "high",
                "trigger_type": "scheduled_scan",
                "evidence": {},
                "suggested_action": "x",
                "analysis": "",
                "start_time": base + timedelta(hours=6 * i),
                "end_time": base + timedelta(hours=6 * (i + 1)),
            }
        )

    ctx = build_historical_context(
        mongo_client=mongo,
        mt5_login=LOGIN,
        window_start=base + timedelta(hours=36),  # after all 5
        window_end=base + timedelta(hours=42),
        risk_keys=("scalping",),
    )
    trend = ctx["trend_by_risk"]["scalping"]
    assert trend["scans_observed"] == 5
    assert trend["prior_high_or_critical_count"] == 3  # 80, 90, 100


def test_empty_history_yields_zeroed_block():
    mongo = mongomock.MongoClient()
    raw_pulls.ensure_indexes(raw_pulls.get_collection(mongo))

    ctx = build_historical_context(
        mongo_client=mongo,
        mt5_login=LOGIN,
        window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 1, 1, 6, tzinfo=timezone.utc),
        risk_keys=("scalping", "bonus_abuse"),
    )
    assert ctx["lookbacks"]["trade_count_24h"] == 0
    assert ctx["lookbacks"]["raw_pulls_used"] == 0
    assert ctx["trend_by_risk"]["scalping"] == {
        "prior_scores": [],
        "prior_high_or_critical_count": 0,
        "scans_observed": 0,
    }
