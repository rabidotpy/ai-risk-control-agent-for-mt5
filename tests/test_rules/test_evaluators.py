"""Per-risk evaluator tests + 250030 regression for latency arbitrage."""

from __future__ import annotations

import json
from pathlib import Path

from app.rules import (
    bonus_abuse,
    latency_arbitrage,
    profitable_client_pattern,
    scalping,
    swap_arbitrage,
)
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


# -- profitable_client_pattern -------------------------------------------------


def _multi_day_profitable_snapshot(
    *, profit_per_trade: float, n_trades: int = 60, days: int = 5,
    losses_per_day: int = 0, loss_size: float = -30.0,
) -> AccountSnapshot:
    """Helper: build a snapshot spanning N distinct days with mixed wins/losses."""
    trades = []
    per_day = n_trades // days
    for d in range(days):
        for i in range(per_day):
            is_loss = i < losses_per_day
            trades.append(make_trade(
                trade_id=d * 100 + i,
                open_time=f"2026-05-{15 + d:02d}T10:{i:02d}:00Z",
                close_time=f"2026-05-{15 + d:02d}T10:{i:02d}:30Z",
                profit=loss_size if is_loss else profit_per_trade,
            ))
    return AccountSnapshot.model_validate(make_snapshot_payload(
        trades=trades,
        start_time="2026-05-15T00:00:00Z",
        end_time=f"2026-05-{15 + days:02d}T00:00:00Z",
    ))


def test_pcp_empty_snapshot_all_insufficient_score_zero():
    out = _by_rule(profitable_client_pattern.evaluate(_snap()))
    for o in out.values():
        assert o.true is False
        assert "insufficient_data" in o.reason


def test_pcp_textbook_profitable_trader_all_four_fire():
    """All 4 sub-rules fire: high rate, sufficient sample + edge,
    distributed wins, consistent days."""
    # 60 trades across 5 days, 50 wins ($30 each), 10 losses ($-60 each)
    snap = _multi_day_profitable_snapshot(
        profit_per_trade=30.0, n_trades=60, days=5,
        losses_per_day=2, loss_size=-60.0,
    )
    # Sanity: 50 wins of 30 = 1500; 10 losses of -60 = -600; net = 900
    # 900 / 5 days = $180/day  (>= 100, fires R1)
    # PF = 1500/600 = 2.5  (>= 1.2, fires R2 since trades = 60 >= 50)
    # biggest single win = 30, total wins = 1500, share = 2%  (<= 30%, fires R3)
    # 5/5 days profitable (every day has 10 wins + 2 losses, net positive)  (fires R4)
    out = _by_rule(profitable_client_pattern.evaluate(snap))
    fired = {r for r, o in out.items() if o.true}
    assert fired == set(profitable_client_pattern.SUB_RULES)


def test_pcp_slow_grinder_below_money_threshold_scores_75():
    """Profit per day below $100, other 3 rules fire. 3/4 = high."""
    # 60 trades / 5 days; want net profit < $500 (so per-day < $100)
    # 30 wins of $10 = 300; 30 losses of $-5 = -150; net = 150; /5 = $30/day
    trades = []
    for d in range(5):
        for i in range(12):
            is_loss = i < 6
            trades.append(make_trade(
                trade_id=d * 100 + i,
                open_time=f"2026-05-{15 + d:02d}T10:{i:02d}:00Z",
                close_time=f"2026-05-{15 + d:02d}T10:{i:02d}:30Z",
                profit=-5.0 if is_loss else 10.0,
            ))
    snap = AccountSnapshot.model_validate(make_snapshot_payload(
        trades=trades,
        start_time="2026-05-15T00:00:00Z",
        end_time="2026-05-20T00:00:00Z",
    ))
    out = _by_rule(profitable_client_pattern.evaluate(snap))
    fired = [r for r, o in out.items() if o.true]
    # R1 (rate $30/day) should NOT fire; the other three should
    assert "profit_extraction_rate >= 100" not in fired
    assert "trade_count >= 50 AND profit_factor >= 1.2" in fired
    assert "biggest_single_win_share <= 0.30" in fired
    assert "profitable_days_ratio >= 0.60" in fired


def test_pcp_one_shot_lucky_wins_only_r1():
    """A single huge winning trade: R1 may fire (big number / short window),
    but the other 3 should NOT (one trade is 100% of profit, sample too small,
    only one day)."""
    trades = [
        make_trade(
            trade_id=1,
            open_time="2026-05-15T10:00:00Z",
            close_time="2026-05-15T10:01:00Z",
            profit=5000.0,
        ),
    ] + [
        # A few small losses to round out the picture
        make_trade(
            trade_id=10 + i,
            open_time=f"2026-05-15T11:{i:02d}:00Z",
            close_time=f"2026-05-15T11:{i:02d}:30Z",
            profit=-50.0,
        )
        for i in range(5)
    ]
    snap = AccountSnapshot.model_validate(make_snapshot_payload(
        trades=trades,
        start_time="2026-05-15T00:00:00Z",
        end_time="2026-05-16T00:00:00Z",  # 1 day
    ))
    out = _by_rule(profitable_client_pattern.evaluate(snap))
    # R1: $4750 / 1 day = $4750/day → fires
    assert out["profit_extraction_rate >= 100"].true is True
    # R2: 6 trades, well below 50 → does NOT fire
    assert out["trade_count >= 50 AND profit_factor >= 1.2"].true is False
    # R3: one win of 5000 = 100% of total gross wins → does NOT fire
    assert out["biggest_single_win_share <= 0.30"].true is False
    # R4: 1 trading day, below the 3-day minimum → insufficient_data
    assert out["profitable_days_ratio >= 0.60"].true is False
    assert "insufficient_data" in out["profitable_days_ratio >= 0.60"].reason


def test_pcp_losing_trader_does_not_fire():
    """A net-losing trader should not trip the profit-focused rules."""
    # 50 wins of 10, 50 losses of 20 -> net -500
    trades = (
        [make_trade(trade_id=i, profit=10.0,
                    open_time=f"2026-05-{15 + (i % 5):02d}T10:{i:02d}:00Z",
                    close_time=f"2026-05-{15 + (i % 5):02d}T10:{i:02d}:30Z")
         for i in range(50)]
        + [make_trade(trade_id=100 + i, profit=-20.0,
                      open_time=f"2026-05-{15 + (i % 5):02d}T11:{i:02d}:00Z",
                      close_time=f"2026-05-{15 + (i % 5):02d}T11:{i:02d}:30Z")
           for i in range(50)]
    )
    snap = AccountSnapshot.model_validate(make_snapshot_payload(
        trades=trades,
        start_time="2026-05-15T00:00:00Z",
        end_time="2026-05-20T00:00:00Z",
    ))
    out = _by_rule(profitable_client_pattern.evaluate(snap))
    assert out["profit_extraction_rate >= 100"].true is False  # negative rate
    assert out["trade_count >= 50 AND profit_factor >= 1.2"].true is False  # PF < 1
    # R3 may still fire (wins are distributed) — that's the rule, not a bug
    # R4 fails (every day is net negative)


def test_pcp_account_250031_regression():
    """The real account 250031 (12 days, 215 trades) must trip all 4.

    Fixture was built once from a Best Wing Global Markets deals export
    and committed alongside this test. It is the canonical "profitable
    client" benchmark for this rule.
    """
    path = Path(__file__).parent / "account_250031_request.json"
    if not path.exists():
        import pytest
        pytest.skip("250031 fixture missing; check tests/test_rules/")
    data = json.loads(path.read_text())
    snap = AccountSnapshot.model_validate(data["snapshot"])
    out = _by_rule(profitable_client_pattern.evaluate(snap))
    fired = [r for r, o in out.items() if o.true]
    assert len(fired) == 4, (
        f"expected all 4 sub-rules to fire on account 250031; got {fired}"
    )
