"""Deterministic evaluation of the Swap Arbitrage rules.

Rule set (unchanged from the prior prompt-based version):
  R1: swap_profit_ratio >= 0.6
  R2: positions_held_across_rollover >= 1
  R3: swap_dominant_closed_positions >= 5
  R4: average_price_movement_pnl_low  (-0.2 <= price_pnl/positive_swap <= 0.2)
"""

from __future__ import annotations

from . import metrics
from .types import RuleOutcome, insufficient


SUB_RULES = (
    "swap_profit_ratio >= 0.6",
    "positions_held_across_rollover >= 1",
    "swap_dominant_closed_positions >= 5",
    "average_price_movement_pnl_low",
)


def evaluate(snapshot) -> list[RuleOutcome]:
    out: list[RuleOutcome] = []

    rule = SUB_RULES[0]
    ratio = metrics.swap_profit_ratio(snapshot)
    if ratio is None:
        out.append(insufficient(rule, "no net positive profit in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(ratio, 4),
                true=ratio >= 0.6,
                reason=f"swap accounts for {ratio:.2%} of total profit",
            )
        )

    rule = SUB_RULES[1]
    if not snapshot.trades:
        out.append(insufficient(rule, "no trades in window"))
    else:
        count = metrics.held_across_rollover_count(snapshot)
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=count,
                true=count >= 1,
                reason=f"{count} positions span at least one UTC midnight",
            )
        )

    rule = SUB_RULES[2]
    if not snapshot.trades:
        out.append(insufficient(rule, "no trades in window"))
    else:
        count = metrics.swap_dominant_count(snapshot)
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=count,
                true=count >= 5,
                reason=f"{count} positions where positive swap dwarfs price PnL",
            )
        )

    rule = SUB_RULES[3]
    pmr = metrics.price_movement_pnl_ratio(snapshot)
    if pmr is None:
        out.append(insufficient(rule, "no positive-swap activity in window"))
    else:
        passes = -0.2 <= pmr <= 0.2
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(pmr, 4),
                true=passes,
                reason=f"price PnL is {pmr:+.2%} of positive swap",
            )
        )

    return out
