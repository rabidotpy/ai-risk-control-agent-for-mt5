"""Pure metric functions over an AccountSnapshot.

Each function returns a number (or None when the input does not support the
metric). The per-risk evaluators in `app/rules/<risk>.py` compose these into
`RuleOutcome`s with threshold checks. No I/O, no side effects, fully
unit-testable in isolation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Iterable, Literal

from ..schemas import AccountSnapshot, Trade


ExitReason = Literal["take_profit", "stop_loss", "manual"]


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


# -----------------------------------------------------------------------------
# Metrics used by the profitable_client_pattern rule.
# These are strategy-agnostic: they describe how meaningful and how repeatable
# the trader's edge is, not which strategy they are running.
# -----------------------------------------------------------------------------


def derive_exit_reason(trade: Trade, *, relative_tolerance: float = 0.0005) -> ExitReason:
    """Classify how a trade was exited.

    Primary signal: the broker tags the `comment` field with `[tp ...]` or
    `[sl ...]` when the auto-orders fired. This is what most MT5 brokers do
    and was verified at 100% accuracy on a real Best Wing Global Markets
    deals export.

    Secondary signal (used when the comment is empty): compare `close_price`
    to the `take_profit` / `stop_loss` values from the open, allowing a small
    relative tolerance for slippage. The tolerance is relative to the entry
    price so it scales correctly across instruments (e.g. gold near 4500 vs
    EURUSD near 1.08).
    """
    c = (trade.comment or "").lower()
    if "[tp" in c:
        return "take_profit"
    if "[sl" in c:
        return "stop_loss"
    tol = trade.open_price * relative_tolerance
    if trade.take_profit and abs(trade.close_price - trade.take_profit) <= tol:
        return "take_profit"
    if trade.stop_loss and abs(trade.close_price - trade.stop_loss) <= tol:
        return "stop_loss"
    return "manual"


def _window_days(snapshot: AccountSnapshot) -> float:
    return (snapshot.end_time - snapshot.start_time).total_seconds() / 86400


def total_profit_per_day(snapshot: AccountSnapshot) -> float | None:
    """Net profit averaged over the window length, in dollars per day.

    None when there are no trades or the window is non-positive (bad input).
    The metric can be negative when the trader is losing.
    """
    if not snapshot.trades:
        return None
    days = _window_days(snapshot)
    if days <= 0:
        return None
    return sum(t.profit for t in snapshot.trades) / days


def profit_factor(snapshot: AccountSnapshot) -> float | None:
    """Gross wins divided by absolute value of gross losses.

    A profit factor of 1.0 is breakeven; 1.2 or above usually indicates a
    real edge in retail trading. None when there are no trades. Returns
    None (rather than infinity) when there are wins but no losses — the
    sample is too one-sided to compute a meaningful ratio.
    """
    if not snapshot.trades:
        return None
    gross_wins = sum(t.profit for t in snapshot.trades if t.profit > 0)
    gross_losses = sum(t.profit for t in snapshot.trades if t.profit < 0)
    if gross_losses == 0:
        # All wins or no wins at all — ratio is undefined / not informative.
        return None
    return gross_wins / abs(gross_losses)


def biggest_single_win_share(snapshot: AccountSnapshot) -> float | None:
    """Largest single winning trade's share of total gross wins.

    Catches the "one lucky trade carries the P&L" case. A small share means
    the edge is spread across many trades, which is the hallmark of a real
    repeatable strategy. None when there are no winning trades.
    """
    wins = [t.profit for t in snapshot.trades if t.profit > 0]
    if not wins:
        return None
    return max(wins) / sum(wins)


def profitable_days_ratio(
    snapshot: AccountSnapshot, *, min_trading_days: int = 3
) -> float | None:
    """Fraction of trading days whose net P&L is positive.

    A trading day is any UTC date with at least one closed trade. The metric
    requires at least `min_trading_days` distinct days in the snapshot to be
    statistically meaningful; otherwise returns None.
    """
    if not snapshot.trades:
        return None
    daily: dict = defaultdict(float)
    for t in snapshot.trades:
        daily[t.close_time.date()] += t.profit
    if len(daily) < min_trading_days:
        return None
    profitable = sum(1 for pnl in daily.values() if pnl > 0)
    return profitable / len(daily)


def manual_close_count(snapshot: AccountSnapshot) -> int:
    """How many trades were closed manually (neither TP nor SL fired)."""
    return sum(1 for t in snapshot.trades if derive_exit_reason(t) == "manual")


def manual_close_win_rate(snapshot: AccountSnapshot) -> float | None:
    """Fraction of manually-closed trades that ended profitable.

    A skilled discretionary trader almost never manually closes a losing
    trade — they let losers run to the stop. The metric is undefined when
    there are no manual closes in the window.
    """
    manuals = [t for t in snapshot.trades if derive_exit_reason(t) == "manual"]
    if not manuals:
        return None
    wins = sum(1 for t in manuals if t.profit > 0)
    return wins / len(manuals)
