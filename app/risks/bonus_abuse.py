"""Bonus / Credit Abuse."""

from __future__ import annotations

from ..rules import bonus_abuse as _eval
from .base import Risk


SUB_RULES = _eval.SUB_RULES


_RISK_PROMPT = """\
RISK BEING EVALUATED: Bonus / Credit Abuse

Bonus abuse means a trader uses promotional bonus or credit to inflate
margin, then trades aggressively to convert the bonus into withdrawable
equity, often via multi-account hedging or rapid withdrawal once the
balance reaches a target.

The longer-window rolling view (last bonus → trade burst, withdrawal
follow-up over days) lives in `prior_behavior_summary`. When folding the
new summary, capture multi-window bonus / withdrawal patterns there so
the next run sees them.

The rule engine has already decided these 5 rules for this window. Use
`rule_outcomes` to narrate; do not re-evaluate.

R1: bonus_received_in_window
   Any bonus event in the window.

R2: trades_after_bonus_in_window >= 8
   Trades opened at or after the earliest bonus event in the window.

R3: linked_account_count >= 2
   Number of broker-flagged linked accounts.

R4: linked_with_opposing_trades >= 1
   Linked accounts whose opposing_trade_count >= 1.

R5: withdrawal_after_bonus_in_window
   Any withdrawal whose time is at or after the earliest bonus event.
"""


BONUS_ABUSE = Risk(
    name="Bonus / Credit Abuse",
    key="bonus_abuse",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
    evaluator=_eval.evaluate,
)
