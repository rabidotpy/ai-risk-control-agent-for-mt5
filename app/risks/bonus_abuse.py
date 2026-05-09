"""Bonus / Credit Abuse — PRD §6.3.

Phase B upgrades:
  R2 — was `trades_after_bonus_in_window >= 8` (6h-proportional).
       Now `trades_within_24h_after_bonus >= 30` (literal PRD threshold);
       reads from `historical_context.lookbacks.trades_within_24h_after_bonus`.
  R5 — was a 6h-cropped check. Now reads
       `historical_context.lookbacks.withdrawal_within_72h_of_bonus`
       so the full 72h span is honoured.
"""

from __future__ import annotations

from .base import Risk, with_trend_rule


_BASE_SUB_RULES = (
    "bonus_received_in_window",
    "trades_within_24h_after_bonus >= 30",
    "linked_account_count >= 2",
    "linked_with_opposing_trades >= 1",
    "withdrawal_within_72h_of_bonus",
)


_BASE_RISK_PROMPT = """\
RISK BEING EVALUATED: Bonus / Credit Abuse

Bonus abuse means a trader uses promotional bonus or credit to inflate
margin, then trades aggressively to convert the bonus into withdrawable
equity, often via multi-account hedging or rapid withdrawal once the
balance reaches a target.

Inputs:
  * `current_window.bonus`            — bonus events in the 6h window
  * `current_window.linked_accounts`  — broker-flagged linked accounts
  * `historical_context.lookbacks`    — 24h / 72h aggregations from the
                                        local raw-pull cache. Required for
                                        R2 and R5.

Evaluate exactly these 6 rules. They are independent.

R1: bonus_received_in_window
   TRUE iff `current_window.bonus` is non-empty.
   If empty: FALSE (with reason "no bonus events in window").

R2: trades_within_24h_after_bonus >= 30
   value = `historical_context.lookbacks.trades_within_24h_after_bonus`.
   TRUE iff value >= 30.
   If `historical_context` is null OR `most_recent_bonus_time` is null:
     FALSE + "insufficient_data: no bonus event in last 30 days".

R3: linked_account_count >= 2
   count = len(current_window.linked_accounts).
   TRUE iff count >= 2.
   If `current_window.linked_accounts` is empty:
     FALSE (with reason "no linked accounts reported").

R4: linked_with_opposing_trades >= 1
   count = number of entries in `current_window.linked_accounts` with
   opposing_trade_count >= 1.
   TRUE iff count >= 1.
   If `current_window.linked_accounts` is empty:
     FALSE (with reason "no linked accounts reported").

R5: withdrawal_within_72h_of_bonus
   value = `historical_context.lookbacks.withdrawal_within_72h_of_bonus`
   (boolean), supported by `hours_bonus_to_withdrawal` for the observed_value.
   TRUE iff value is true.
   If `historical_context` is null OR `most_recent_bonus_time` is null:
     FALSE + "insufficient_data: no bonus event in last 30 days".
"""


SUB_RULES, _RISK_PROMPT = with_trend_rule(
    key="bonus_abuse",
    sub_rules=_BASE_SUB_RULES,
    risk_prompt=_BASE_RISK_PROMPT,
)


BONUS_ABUSE = Risk(
    name="Bonus / Credit Abuse",
    key="bonus_abuse",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
)
