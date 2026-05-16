"""Deterministic evaluation of the Scalping Violation rules.

Rule set (unchanged from the prior prompt-based version):
  R1: trade_count_in_window >= 25
  R2: short_holding_ratio_60s >= 0.7
  R3: win_rate >= 0.75
  R4: repeated_lot_sl_tp_pattern_ratio >= 0.5
"""

from __future__ import annotations

from . import metrics
from .types import RuleOutcome, insufficient


SUB_RULES = (
    "trade_count_in_window >= 25",
    "short_holding_ratio_60s >= 0.7",
    "win_rate >= 0.75",
    "repeated_lot_sl_tp_pattern_ratio >= 0.5",
)


def evaluate(snapshot) -> list[RuleOutcome]:
    out: list[RuleOutcome] = []

    count = metrics.trade_count(snapshot)
    out.append(
        RuleOutcome(
            rule=SUB_RULES[0],
            observed_value=count,
            true=count >= 25,
            reason=f"{count} closed positions in window",
        )
    )

    rule = SUB_RULES[1]
    ratio = metrics.short_holding_ratio(snapshot, threshold_seconds=60)
    if ratio is None:
        out.append(insufficient(rule, "no trades in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(ratio, 4),
                true=ratio >= 0.7,
                reason=f"{ratio:.2%} of trades held <= 60s",
            )
        )

    rule = SUB_RULES[2]
    if len(snapshot.trades) < 5:
        out.append(insufficient(rule, "fewer than 5 trades — win rate not meaningful"))
    else:
        wr = metrics.win_rate(snapshot) or 0.0
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(wr, 4),
                true=wr >= 0.75,
                reason=f"win rate {wr:.2%}",
            )
        )

    rule = SUB_RULES[3]
    if len(snapshot.trades) < 3:
        out.append(insufficient(rule, "fewer than 3 trades — pattern detection not meaningful"))
    else:
        pr = metrics.repeated_lot_sl_tp_pattern_ratio(snapshot) or 0.0
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(pr, 4),
                true=pr >= 0.5,
                reason=f"{pr:.2%} of trades share a (volume, SL, TP) bucket",
            )
        )

    return out
