"""Latency Arbitrage."""

from __future__ import annotations

from ..rules import latency_arbitrage as _eval
from .base import Risk


SUB_RULES = _eval.SUB_RULES


_RISK_PROMPT = """\
RISK BEING EVALUATED: Latency Arbitrage

Latency arbitrage means a trader profits by exploiting stale or delayed
quotes. The fingerprint is: high frequency, very short holds, near-100%
win rate, both buy and sell sides traded, and trades closed one at a
time rather than in batches. A martingale grid looks superficially
similar (many short positions, many wins) but is one-sided and closes
in batches; the rules below are tuned to separate the two.

The rule engine has already decided these 4 rules for this window. Use
`rule_outcomes` to narrate; do not re-evaluate.

R1: trade_count_in_window >= 30
   Total number of closed positions in the window.

R2: median_holding_time_seconds <= 30
   Median of (close_time − open_time) across the window's trades.

R3: minority_side_ratio >= 0.2
   min(buy_count, sell_count) / total_trades. A real latency-arb account
   trades both sides; a one-sided grid will score near 0.

R4: win_rate >= 0.9 AND batch_close_ratio <= 0.2
   Composite: win_rate is wins / total; batch_close_ratio is the fraction
   of trades whose close_time second is shared by 3+ other trades. A real
   latency-arb account wins almost everything AND closes trades one at a
   time. A grid wins often but closes in batches (high batch ratio), so
   it fails this composite.
"""


LATENCY_ARBITRAGE = Risk(
    name="Latency Arbitrage",
    key="latency_arbitrage",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
    evaluator=_eval.evaluate,
)
