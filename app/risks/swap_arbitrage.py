"""Swap Arbitrage."""

from __future__ import annotations

from .base import Risk


SUB_RULES = (
    "swap_profit_ratio >= 0.6",
    "positions_held_across_rollover >= 1",
    "swap_dominant_closed_positions >= 5",
    "average_price_movement_pnl_low",
)


_RISK_PROMPT = """\
RISK BEING EVALUATED: Swap Arbitrage

Swap arbitrage means the trader profits primarily from positive overnight
swap (rollover interest), not from price movement. Fingerprints: a large
share of total profit comes from the `swaps` field, positions are held
across daily rollover, the price movement P&L on the same trades is small
relative to the swap, and instruments are typically chosen for their
positive carry rate.

Each row in `current_window.trades` carries:
  swaps      — total swap interest accrued over the position's life
  commission — per-trade commission (negative = charge, treat 0 as 0)
  profit     — realized PnL on close, NET of swap and commission

Therefore: price_pnl = profit − swaps − commission. This isolates the
P&L attributable purely to price movement.

Evaluate exactly these 4 rules. They are independent.

R1: swap_profit_ratio >= 0.6
   total_swap   = sum(t.swaps   for t in current_window.trades)
   total_profit = sum(t.profit  for t in current_window.trades)
   ratio = total_swap / total_profit (only when total_profit > 0).
   TRUE iff total_profit > 0 AND ratio >= 0.6.
   If total_profit <= 0 or `current_window.trades` is empty:
     FALSE + "insufficient_data: no net positive profit in window".

R2: positions_held_across_rollover >= 1
   A trade is "held across rollover" iff its open_time and close_time fall
   on different UTC calendar dates.
   count = number of such trades in `current_window.trades`.
   TRUE iff count >= 1.
   If `current_window.trades` is empty: FALSE + "insufficient_data: no trades in window".

R3: swap_dominant_closed_positions >= 5
   For each trade in `current_window.trades`, compute price_pnl = profit − swaps − commission.
   The trade is "swap-dominant" iff swaps > 0 AND |price_pnl| <= 0.1 * swaps.
   (Positive swap only — negative swap means the client is paying carry,
   which is the opposite of arbitrage.)
   count = number of swap-dominant trades.
   TRUE iff count >= 5.
   If `current_window.trades` is empty: FALSE + "insufficient_data: no trades in window".

R4: average_price_movement_pnl_low
   Restrict to trades in `current_window.trades` with swaps > 0.
   total_price_pnl     = sum of price_pnl over those trades
   total_positive_swap = sum of swaps over those trades
   ratio = total_price_pnl / total_positive_swap (only when total_positive_swap > 0).
   TRUE iff total_positive_swap > 0 AND -0.2 <= ratio <= 0.2 (the price-movement
   P&L is small relative to swap, in either direction).
   If total_positive_swap <= 0 or `current_window.trades` is empty:
     FALSE + "insufficient_data: no positive-swap activity".
"""


SWAP_ARBITRAGE = Risk(
    name="Swap Arbitrage",
    key="swap_arbitrage",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
)
