"""Per-risk evaluator tests + 250030 regression for latency arbitrage."""

from __future__ import annotations

import json
from pathlib import Path

from app.rules import bonus_abuse, latency_arbitrage, scalping, swap_arbitrage
from app.schemas import AccountSnapshot

from ..conftest import make_short_trades, make_snapshot_payload, make_trade


def _snap(**kw) -> AccountSnapshot:
    return AccountSnapshot.model_validate(make_snapshot_payload(**kw))


def _by_rule(outcomes):
    return {o.rule: o for o in outcomes}


# -- latency arbitrage --------------------------------------------------------


def test_latency_empty_window_only_r1_decidable():
    out = _by_rule(latency_arbitrage.evaluate(_snap()))
    assert out["trade_count_in_window >= 30"].true is False
    # Other three return insufficient
    for k in (
        "median_holding_time_seconds <= 30",
        "minority_side_ratio >= 0.2",
        "win_rate >= 0.9 AND batch_close_ratio <= 0.2",
    ):
        assert out[k].true is False
        assert "insufficient_data" in out[k].reason


def test_latency_full_trip_real_arbitrage_pattern():
    """30 short, both-sided, all-winning, scattered closes → 4/4 trip."""
    trades = make_short_trades(30, side="buy", profit=1.0)
    for i in range(0, 30, 2):
        trades[i]["side"] = "sell"
    out = _by_rule(latency_arbitrage.evaluate(_snap(trades=trades)))
    assert all(o.true for o in out.values())


def test_latency_grid_pattern_does_not_trip():
    """One-sided, long-hold grid: only R1 fires, score floor."""
    # 30 short shorts, all same direction, ~35 min holds, batch closes
    trades = []
    for i in range(30):
        trades.append(
            make_trade(
                trade_id=i,
                side="sell",
                open_time=f"2026-05-08T01:{i:02d}:00Z",
                close_time="2026-05-08T02:00:00Z",  # all close same second
                profit=1.0,
            )
        )
    out = _by_rule(latency_arbitrage.evaluate(_snap(trades=trades)))
    assert out["trade_count_in_window >= 30"].true is True
    assert out["median_holding_time_seconds <= 30"].true is False
    assert out["minority_side_ratio >= 0.2"].true is False
    assert out["win_rate >= 0.9 AND batch_close_ratio <= 0.2"].true is False


def test_latency_account_250030_regression():
    """The real client xlsx must NOT trip latency arbitrage past R1."""
    path = Path(__file__).parent / "account_250030_snapshot.json"
    data = json.loads(path.read_text())
    snap = AccountSnapshot.model_validate(data["snapshot"])
    out = _by_rule(latency_arbitrage.evaluate(snap))
    fired = [r for r, o in out.items() if o.true]
    assert fired == ["trade_count_in_window >= 30"]


# -- scalping -----------------------------------------------------------------


def test_scalping_full_trip():
    # 25 trades, holds 10s each, all wins, same SL/TP/volume → 4/4 trip
    trades = []
    for i in range(25):
        trades.append(
            make_trade(
                trade_id=i,
                open_time=f"2026-05-08T01:{i:02d}:00Z",
                close_time=f"2026-05-08T01:{i:02d}:10Z",
                volume=0.1,
                stop_loss=1.0,
                take_profit=2.0,
                profit=1.0,
            )
        )
    out = _by_rule(scalping.evaluate(_snap(trades=trades)))
    assert all(o.true for o in out.values())


def test_scalping_insufficient_paths():
    out = _by_rule(scalping.evaluate(_snap()))
    assert "insufficient_data" in out["win_rate >= 0.75"].reason
    assert "insufficient_data" in out["repeated_lot_sl_tp_pattern_ratio >= 0.5"].reason


# -- swap arbitrage -----------------------------------------------------------


def test_swap_full_trip():
    # 5 trades each: held across rollover, positive swap dwarfs price PnL
    trades = []
    for i in range(5):
        trades.append(
            make_trade(
                trade_id=i,
                open_time=f"2026-05-08T22:{i:02d}:00Z",
                close_time=f"2026-05-09T02:{i:02d}:00Z",
                profit=10.05,
                swaps=10.0,
                commission=0.0,
            )
        )
    out = _by_rule(swap_arbitrage.evaluate(_snap(trades=trades)))
    assert all(o.true for o in out.values())


def test_swap_no_positive_profit_marks_r1_insufficient():
    losing = make_short_trades(3, profit=-1.0)
    out = _by_rule(swap_arbitrage.evaluate(_snap(trades=losing)))
    assert "insufficient_data" in out["swap_profit_ratio >= 0.6"].reason


# -- bonus abuse --------------------------------------------------------------


def test_bonus_full_trip():
    bonus = [
        {"id": 1, "login": 70001, "group": "g", "time": "2026-05-08T01:00:00Z", "profit": 100.0}
    ]
    withdraws = [
        {"id": 2, "login": 70001, "group": "g", "time": "2026-05-08T05:00:00Z", "profit": -50.0}
    ]
    trades = [
        make_trade(
            trade_id=10 + i,
            open_time=f"2026-05-08T02:{i:02d}:00Z",
            close_time=f"2026-05-08T02:{i:02d}:30Z",
        )
        for i in range(8)
    ]
    linked = [
        {"login": 99, "link_reasons": ["same_ip"], "opposing_trade_count": 1},
        {"login": 100, "link_reasons": ["same_ip"], "opposing_trade_count": 0},
    ]
    snap = _snap(trades=trades, bonus=bonus, withdraws=withdraws, linked_accounts=linked)
    out = _by_rule(bonus_abuse.evaluate(snap))
    assert all(o.true for o in out.values())


def test_bonus_no_bonus_marks_dependent_rules_insufficient():
    out = _by_rule(bonus_abuse.evaluate(_snap()))
    assert "insufficient_data" in out["trades_after_bonus_in_window >= 8"].reason
    assert "insufficient_data" in out["withdrawal_after_bonus_in_window"].reason
