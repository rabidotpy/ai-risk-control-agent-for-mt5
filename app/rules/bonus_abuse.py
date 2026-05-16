"""Deterministic evaluation of the Bonus / Credit Abuse rules.

Rule set (unchanged from the prior prompt-based version):
  R1: bonus_received_in_window
  R2: trades_after_bonus_in_window >= 8
  R3: linked_account_count >= 2
  R4: linked_with_opposing_trades >= 1
  R5: withdrawal_after_bonus_in_window
"""

from __future__ import annotations

from . import metrics
from .types import RuleOutcome, insufficient


SUB_RULES = (
    "bonus_received_in_window",
    "trades_after_bonus_in_window >= 8",
    "linked_account_count >= 2",
    "linked_with_opposing_trades >= 1",
    "withdrawal_after_bonus_in_window",
)


def evaluate(snapshot) -> list[RuleOutcome]:
    out: list[RuleOutcome] = []

    rule = SUB_RULES[0]
    present = metrics.bonus_received_present(snapshot)
    out.append(
        RuleOutcome(
            rule=rule,
            observed_value=len(snapshot.bonus),
            true=present,
            reason=(
                f"{len(snapshot.bonus)} bonus event(s) in window"
                if present
                else "no bonus events in window"
            ),
        )
    )

    rule = SUB_RULES[1]
    count = metrics.trades_after_bonus_count(snapshot)
    if count is None:
        out.append(insufficient(rule, "no bonus event in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=count,
                true=count >= 8,
                reason=f"{count} trades opened at or after earliest bonus",
            )
        )

    rule = SUB_RULES[2]
    la_count = metrics.linked_account_count(snapshot)
    if la_count == 0:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=0,
                true=False,
                reason="no linked accounts reported",
            )
        )
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=la_count,
                true=la_count >= 2,
                reason=f"{la_count} linked account(s) reported",
            )
        )

    rule = SUB_RULES[3]
    if metrics.linked_account_count(snapshot) == 0:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=0,
                true=False,
                reason="no linked accounts reported",
            )
        )
    else:
        opp = metrics.linked_with_opposing_count(snapshot)
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=opp,
                true=opp >= 1,
                reason=f"{opp} linked account(s) with opposing trades",
            )
        )

    rule = SUB_RULES[4]
    wab = metrics.withdrawal_after_bonus_present(snapshot)
    if wab is None:
        out.append(insufficient(rule, "no bonus event in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=wab,
                true=wab,
                reason=(
                    "at least one withdrawal happens after earliest bonus"
                    if wab
                    else "no withdrawals happen after earliest bonus"
                ),
            )
        )

    return out
