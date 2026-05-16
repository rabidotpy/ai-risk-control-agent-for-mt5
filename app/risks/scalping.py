"""Scalping Violation."""

from __future__ import annotations

from ..rules import scalping as _eval
from .base import Risk


SUB_RULES = _eval.SUB_RULES


_RISK_PROMPT = """\
RISK BEING EVALUATED: Scalping Violation

Scalping in this context means very short positions, very high frequency,
small per-trade profits, and a high win rate, often with a fixed pattern
(same volume, same SL, same TP). Whether scalping is a contractual
violation depends on the customer agreement; this evaluation flags the
pattern only.

The rule engine has already decided these 4 rules for this window. Use
`rule_outcomes` to narrate; do not re-evaluate.

R1: trade_count_in_window >= 25
   Total number of closed positions in the window.

R2: short_holding_ratio_60s >= 0.7
   Fraction of trades with holding_seconds <= 60.

R3: win_rate >= 0.75
   Fraction of trades with profit > 0. Needs at least 5 trades to be
   meaningful.

R4: repeated_lot_sl_tp_pattern_ratio >= 0.5
   Fraction of trades that share a (volume, stop_loss, take_profit)
   bucket with 3+ other trades. Needs at least 3 trades.
"""


SCALPING = Risk(
    name="Scalping Violation",
    key="scalping",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
    evaluator=_eval.evaluate,
)
