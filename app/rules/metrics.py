"""Pure metric functions over an AccountSnapshot.

Each function returns a number (or None when the input does not support the
metric). The per-risk evaluators in `app/rules/<risk>.py` compose these into
`RuleOutcome`s with threshold checks. No I/O, no side effects, fully
unit-testable in isolation.
"""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Iterable

from ..schemas import AccountSnapshot, Trade


def _holding_seconds(trade: Trade) -> float:
    return (trade.close_time - trade.open_time).total_seconds()


def trade_count(snapshot: AccountSnapshot) -> int:
    return len(snapshot.trades)


def median_holding_seconds(snapshot: AccountSnapshot) -> float | None:
    if not snapshot.trades:
        return None
    return float(median(_holding_seconds(t) for t in snapshot.trades))


def short_holding_ratio(snapshot: AccountSnapshot, *, threshold_seconds: float) -> float | None:
    if not snapshot.trades:
        return None
    short = sum(1 for t in snapshot.trades if _holding_seconds(t) <= threshold_seconds)
    return short / len(snapshot.trades)


def minority_side_ratio(snapshot: AccountSnapshot) -> float | None:
    """Fraction of trades on the less-traded side.

    1.0 means a perfect 50/50 split; 0.0 means one side only. Used to detect
    one-sided strategies (martingale grids, persistent directional bets) that
    do not match the opportunistic both-sides signature of latency arbitrage.
    """
    if not snapshot.trades:
        return None
    counts = Counter(t.side for t in snapshot.trades)
    minority = min(counts.get("buy", 0), counts.get("sell", 0))
    return minority / len(snapshot.trades)


def win_rate(snapshot: AccountSnapshot) -> float | None:
    if not snapshot.trades:
        return None
    wins = sum(1 for t in snapshot.trades if t.profit > 0)
    return wins / len(snapshot.trades)


def batch_close_ratio(snapshot: AccountSnapshot) -> float | None:
    """Fraction of trades whose close_time second is shared by >=2 other trades.

    A grid trader closes many positions together; an arbitrageur closes them
    one at a time. High values mean grid-style behaviour.
    """
    if not snapshot.trades:
        return None
    second_counts = Counter(
        t.close_time.replace(microsecond=0) for t in snapshot.trades
    )
    in_batch = sum(
        1
        for t in snapshot.trades
        if second_counts[t.close_time.replace(microsecond=0)] >= 3
    )
    return in_batch / len(snapshot.trades)


def repeated_lot_sl_tp_pattern_ratio(snapshot: AccountSnapshot) -> float | None:
    """Fraction of trades whose (volume, SL, TP) triple is shared by >=3 trades.

    SL and TP are normalised: 0.0 and None are treated as identical (both mean
    "unset", per the real MT5 admin export).
    """
    if not snapshot.trades:
        return None

    def _bucket_key(t: Trade) -> tuple[float, float, float]:
        sl = t.stop_loss or 0.0
        tp = t.take_profit or 0.0
        return (t.volume, sl, tp)

    buckets = Counter(_bucket_key(t) for t in snapshot.trades)
    in_pattern = sum(1 for t in snapshot.trades if buckets[_bucket_key(t)] >= 3)
    return in_pattern / len(snapshot.trades)


def swap_profit_ratio(snapshot: AccountSnapshot) -> float | None:
    """total_swap / total_profit, only defined when total_profit > 0."""
    if not snapshot.trades:
        return None
    total_profit = sum(t.profit for t in snapshot.trades)
    if total_profit <= 0:
        return None
    total_swap = sum(t.swaps for t in snapshot.trades)
    return total_swap / total_profit


def held_across_rollover_count(snapshot: AccountSnapshot) -> int:
    """Trades whose open_time and close_time fall on different UTC dates."""
    return sum(
        1
        for t in snapshot.trades
        if t.open_time.date() != t.close_time.date()
    )


def swap_dominant_count(snapshot: AccountSnapshot) -> int:
    """Trades where positive swap dwarfs price PnL (|price_pnl| <= 10% of swap)."""
    count = 0
    for t in snapshot.trades:
        if t.swaps <= 0:
            continue
        price_pnl = t.profit - t.swaps - t.commission
        if abs(price_pnl) <= 0.1 * t.swaps:
            count += 1
    return count


def price_movement_pnl_ratio(snapshot: AccountSnapshot) -> float | None:
    """sum(price_pnl) / sum(positive_swap) across trades with positive swap.

    None when no trade carries positive swap (the metric is undefined).
    """
    pos_swap_trades = [t for t in snapshot.trades if t.swaps > 0]
    if not pos_swap_trades:
        return None
    total_positive_swap = sum(t.swaps for t in pos_swap_trades)
    if total_positive_swap <= 0:
        return None
    total_price_pnl = sum(
        t.profit - t.swaps - t.commission for t in pos_swap_trades
    )
    return total_price_pnl / total_positive_swap


def _earliest_bonus_time(snapshot: AccountSnapshot):
    if not snapshot.bonus:
        return None
    return min(b.time for b in snapshot.bonus)


def trades_after_bonus_count(snapshot: AccountSnapshot) -> int | None:
    """Trades opened at or after the earliest bonus event in the window.

    None when there is no bonus event in the window — the metric is undefined.
    """
    bonus_time = _earliest_bonus_time(snapshot)
    if bonus_time is None:
        return None
    return sum(1 for t in snapshot.trades if t.open_time >= bonus_time)


def linked_account_count(snapshot: AccountSnapshot) -> int:
    return len(snapshot.linked_accounts)


def linked_with_opposing_count(snapshot: AccountSnapshot) -> int:
    return sum(
        1 for la in snapshot.linked_accounts if la.opposing_trade_count >= 1
    )


def withdrawal_after_bonus_present(snapshot: AccountSnapshot) -> bool | None:
    """True iff a withdrawal happens at or after the earliest bonus.

    None when there is no bonus event in the window (undefined).
    """
    bonus_time = _earliest_bonus_time(snapshot)
    if bonus_time is None:
        return None
    return any(w.time >= bonus_time for w in snapshot.withdraws)


def bonus_received_present(snapshot: AccountSnapshot) -> bool:
    return len(snapshot.bonus) > 0
