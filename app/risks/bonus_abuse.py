"""Bonus / Credit Abuse."""

from __future__ import annotations

from .base import Risk


SUB_RULES = (
    "bonus_received_in_window",
    "trades_after_bonus_in_window >= 8",
    "linked_account_count >= 2",
    "linked_with_opposing_trades >= 1",
    "withdrawal_after_bonus_in_window",
)


_RISK_PROMPT = """\
RISK BEING EVALUATED: Bonus / Credit Abuse

Bonus abuse means a trader uses promotional bonus or credit to inflate
margin, then trades aggressively to convert the bonus into withdrawable
equity, often via multi-account hedging or rapid withdrawal once the
balance reaches a target.

Inputs (all from `current_window`):
  * bonus            — bonus events in the window
  * trades           — closed positions in the window
  * withdraws        — withdrawal events in the window
  * linked_accounts  — broker-flagged linked accounts

The longer-window rolling view (last bonus → trade burst, withdrawal
follow-up over days) lives in `prior_behavior_summary`. When folding the
new summary, capture multi-window bonus / withdrawal patterns there so
the next run sees them.

Evaluate exactly these 5 rules. They are independent.

R1: bonus_received_in_window
   TRUE iff `current_window.bonus` is non-empty.
   If empty: FALSE (with reason "no bonus events in window").

R2: trades_after_bonus_in_window >= 8
   If `current_window.bonus` is empty: FALSE + "insufficient_data: no bonus event in window".
   Let earliest_bonus_time = min(b.time for b in current_window.bonus).
   count = number of trades in `current_window.trades` whose
           open_time >= earliest_bonus_time.
   TRUE iff count >= 8.

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

R5: withdrawal_after_bonus_in_window
   If `current_window.bonus` is empty: FALSE + "insufficient_data: no bonus event in window".
   Let earliest_bonus_time = min(b.time for b in current_window.bonus).
   TRUE iff any withdrawal in `current_window.withdraws` has time >= earliest_bonus_time.
"""


BONUS_ABUSE = Risk(
    name="Bonus / Credit Abuse",
    key="bonus_abuse",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
)
