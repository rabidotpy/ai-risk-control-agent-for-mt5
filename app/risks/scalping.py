"""Scalping Violation — PRD §6.3.

R1 is the literal PRD threshold (`trade_count_24h >= 100`); it reads from
`historical_context.lookbacks.trade_count_24h`. Until the local raw-pull
cache contains 24h of pulls (4 scans), R1 returns insufficient_data.
"""

from __future__ import annotations

from .base import Risk, with_trend_rule


_BASE_SUB_RULES = (
    "trade_count_24h >= 100",
    "short_holding_ratio_60s >= 0.7",
    "win_rate >= 0.75",
    "repeated_lot_sl_tp_pattern_ratio >= 0.5",
)


_BASE_RISK_PROMPT = """\
RISK BEING EVALUATED: Scalping Violation

Scalping in this context means very short positions, very high frequency,
small per-trade profits, and a high win rate, often with a fixed pattern
(same volume, same SL, same TP). Whether scalping is a contractual
violation depends on the customer agreement; this evaluation flags the
pattern only.

The current data window is 6 hours; `current_window.trades` is the array
of complete closed positions in that window. The 24h trade count comes
from `historical_context.lookbacks.trade_count_24h`.

Evaluate exactly these 5 rules. They are independent.

R1: trade_count_24h >= 100
   value = `historical_context.lookbacks.trade_count_24h`.
   TRUE iff value >= 100.
   If `historical_context` is null or `trade_count_24h` is missing/null:
     FALSE + "insufficient_data: no historical context yet".

R2: short_holding_ratio_60s >= 0.7
   For every trade in `current_window.trades` compute
   holding_seconds = (close_time − open_time).total_seconds().
   short_count = number of trades with holding_seconds <= 60.
   ratio = short_count / len(current_window.trades).
   TRUE iff ratio >= 0.7.
   If `current_window.trades` is empty: FALSE + "insufficient_data: no trades in window".

R3: win_rate >= 0.75
   wins = number of trades in `current_window.trades` with profit > 0.
   ratio = wins / len(current_window.trades).
   TRUE iff ratio >= 0.75.
   If fewer than 5 trades in `current_window.trades`: FALSE + \
"insufficient_data: fewer than 5 trades — win rate not meaningful".

R4: repeated_lot_sl_tp_pattern_ratio >= 0.5
   Bucket trades in `current_window.trades` by the triple
   (volume, stop_loss, take_profit). When forming bucket keys, treat 0 and
   null as the same value (both mean "unset") — most clients leave SL/TP at 0.
   A "pattern bucket" is one shared by 3 or more trades.
   pattern_count = number of trades belonging to a pattern bucket.
   ratio = pattern_count / len(current_window.trades).
   TRUE iff ratio >= 0.5.
   If fewer than 3 trades in `current_window.trades`: FALSE + \
"insufficient_data: fewer than 3 trades — pattern detection not meaningful".
"""


SUB_RULES, _RISK_PROMPT = with_trend_rule(
    key="scalping",
    sub_rules=_BASE_SUB_RULES,
    risk_prompt=_BASE_RISK_PROMPT,
)


SCALPING = Risk(
    name="Scalping Violation",
    key="scalping",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
)
