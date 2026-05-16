"""Swap Arbitrage."""

from __future__ import annotations

from ..rules import swap_arbitrage as _eval
from .base import Risk


SUB_RULES = _eval.SUB_RULES


_RISK_PROMPT = """\
RISK BEING EVALUATED: Swap Arbitrage

Swap arbitrage means the trader profits primarily from positive overnight
swap (rollover interest), not from price movement. Fingerprints: a large
share of total profit comes from `swaps`, positions are held across daily
rollover, price movement P&L on the same trades is small relative to
swap, and instruments are typically chosen for their positive carry rate.

The rule engine has already decided these 4 rules for this window. Use
`rule_outcomes` to narrate; do not re-evaluate.

R1: swap_profit_ratio >= 0.6
   total_swap / total_profit, when total_profit > 0.

R2: positions_held_across_rollover >= 1
   Count of trades whose open_time and close_time fall on different UTC
   calendar dates.

R3: swap_dominant_closed_positions >= 5
   Count of trades where swaps > 0 AND |price_pnl| <= 0.1 * swaps,
   where price_pnl = profit − swaps − commission.

R4: average_price_movement_pnl_low
   Across trades with swaps > 0, total price_pnl / total positive swap;
   passes when the ratio sits in [-0.2, 0.2].
"""


SWAP_ARBITRAGE = Risk(
    name="Swap Arbitrage",
    key="swap_arbitrage",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
    evaluator=_eval.evaluate,
)
