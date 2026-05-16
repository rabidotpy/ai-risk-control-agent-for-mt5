"""Unit tests for app/rules/metrics.py — one or two cases per metric."""

from __future__ import annotations

from app.rules import metrics
from app.schemas import AccountSnapshot

from ..conftest import make_short_trades, make_snapshot_payload, make_trade


def _snap(**kw) -> AccountSnapshot:
    return AccountSnapshot.model_validate(make_snapshot_payload(**kw))


def test_trade_count_empty_and_nonempty():
    assert metrics.trade_count(_snap()) == 0
    assert metrics.trade_count(_snap(trades=make_short_trades(5))) == 5


def test_median_holding_seconds_none_when_empty():
    assert metrics.median_holding_seconds(_snap()) is None


def test_median_holding_seconds_computed():
    trades = make_short_trades(3, hold_seconds=20)
    assert metrics.median_holding_seconds(_snap(trades=trades)) == 20.0


def test_short_holding_ratio_threshold():
    trades = make_short_trades(4, hold_seconds=10)
    assert metrics.short_holding_ratio(_snap(trades=trades), threshold_seconds=30) == 1.0
    assert metrics.short_holding_ratio(_snap(trades=trades), threshold_seconds=5) == 0.0


def test_short_holding_ratio_none_when_empty():
    assert metrics.short_holding_ratio(_snap(), threshold_seconds=30) is None


def test_minority_side_ratio_one_sided_is_zero():
    trades = make_short_trades(10, side="buy")
    assert metrics.minority_side_ratio(_snap(trades=trades)) == 0.0


def test_minority_side_ratio_balanced_is_half():
    trades = make_short_trades(10)
    for i in range(0, 10, 2):
        trades[i]["side"] = "sell"
    assert metrics.minority_side_ratio(_snap(trades=trades)) == 0.5


def test_win_rate_all_wins_all_losses():
    wins = make_short_trades(4, profit=1.0)
    losses = make_short_trades(4, profit=-1.0)
    assert metrics.win_rate(_snap(trades=wins)) == 1.0
    assert metrics.win_rate(_snap(trades=losses)) == 0.0


def test_batch_close_ratio_grid_vs_scatter():
    # Scattered: each close 1 minute apart → no batching
    scattered = make_short_trades(6)
    assert metrics.batch_close_ratio(_snap(trades=scattered)) == 0.0

    # Batch: 4 trades share the same close second → 4/4 in batch
    batch = [
        make_trade(trade_id=i, close_time="2026-05-08T01:05:00Z") for i in range(4)
    ]
    assert metrics.batch_close_ratio(_snap(trades=batch)) == 1.0


def test_repeated_lot_sl_tp_pattern_ratio():
    # 4 trades same (volume, sl, tp) → all in pattern
    patterned = [
        make_trade(trade_id=i, volume=0.1, stop_loss=1.0, take_profit=2.0)
        for i in range(4)
    ]
    assert metrics.repeated_lot_sl_tp_pattern_ratio(_snap(trades=patterned)) == 1.0
    # Each trade unique → none in a pattern bucket
    unique = [
        make_trade(trade_id=i, volume=0.1 * (i + 1)) for i in range(4)
    ]
    assert metrics.repeated_lot_sl_tp_pattern_ratio(_snap(trades=unique)) == 0.0


def test_swap_profit_ratio_none_when_no_net_profit():
    losing = make_short_trades(3, profit=-1.0)
    assert metrics.swap_profit_ratio(_snap(trades=losing)) is None


def test_swap_profit_ratio_computed():
    trades = [make_trade(trade_id=i, profit=10.0, swaps=6.0) for i in range(3)]
    assert metrics.swap_profit_ratio(_snap(trades=trades)) == 0.6


def test_held_across_rollover_count():
    held = [
        make_trade(
            trade_id=1,
            open_time="2026-05-08T22:00:00Z",
            close_time="2026-05-09T02:00:00Z",
        )
    ]
    intraday = make_short_trades(2)
    assert metrics.held_across_rollover_count(_snap(trades=held)) == 1
    assert metrics.held_across_rollover_count(_snap(trades=intraday)) == 0


def test_swap_dominant_count():
    # Positive swap dwarfs price PnL → counted
    dominant = [
        make_trade(trade_id=i, profit=10.05, swaps=10.0, commission=0.0)
        for i in range(3)
    ]
    # price_pnl = 0.05 ≤ 10% of 10.0 → all 3 dominant
    assert metrics.swap_dominant_count(_snap(trades=dominant)) == 3
    # Negative swap → not counted regardless
    negative = [make_trade(trade_id=i, profit=0.0, swaps=-5.0) for i in range(3)]
    assert metrics.swap_dominant_count(_snap(trades=negative)) == 0


def test_price_movement_pnl_ratio_none_when_no_positive_swap():
    no_swap = make_short_trades(3)
    assert metrics.price_movement_pnl_ratio(_snap(trades=no_swap)) is None


def test_price_movement_pnl_ratio_computed():
    trades = [
        make_trade(trade_id=i, profit=10.05, swaps=10.0, commission=0.0)
        for i in range(3)
    ]
    # total price_pnl = 0.15, total positive swap = 30 → 0.005
    assert abs(metrics.price_movement_pnl_ratio(_snap(trades=trades)) - 0.005) < 1e-9


def test_bonus_and_trades_after_bonus():
    bonus = [
        {"id": 9, "login": 70001, "group": "g", "time": "2026-05-08T02:00:00Z", "profit": 50.0}
    ]
    before = make_trade(trade_id=1, open_time="2026-05-08T01:00:00Z",
                        close_time="2026-05-08T01:01:00Z")
    after = make_trade(trade_id=2, open_time="2026-05-08T03:00:00Z",
                       close_time="2026-05-08T03:01:00Z")
    snap = _snap(trades=[before, after], bonus=bonus)
    assert metrics.bonus_received_present(snap) is True
    assert metrics.trades_after_bonus_count(snap) == 1


def test_trades_after_bonus_none_when_no_bonus():
    assert metrics.trades_after_bonus_count(_snap()) is None


def test_linked_account_helpers():
    linked = [
        {"login": 99, "link_reasons": ["same_ip"], "opposing_trade_count": 0},
        {"login": 100, "link_reasons": ["same_ip"], "opposing_trade_count": 3},
    ]
    snap = _snap(linked_accounts=linked)
    assert metrics.linked_account_count(snap) == 2
    assert metrics.linked_with_opposing_count(snap) == 1


def test_withdrawal_after_bonus():
    bonus = [
        {"id": 9, "login": 70001, "group": "g", "time": "2026-05-08T02:00:00Z", "profit": 50.0}
    ]
    withdraws = [
        {"id": 10, "login": 70001, "group": "g", "time": "2026-05-08T03:00:00Z", "profit": -10.0}
    ]
    snap = _snap(bonus=bonus, withdraws=withdraws)
    assert metrics.withdrawal_after_bonus_present(snap) is True
    assert metrics.withdrawal_after_bonus_present(_snap(bonus=bonus)) is False
    assert metrics.withdrawal_after_bonus_present(_snap(withdraws=withdraws)) is None
