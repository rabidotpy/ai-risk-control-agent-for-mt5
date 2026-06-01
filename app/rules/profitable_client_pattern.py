"""Deterministic evaluation of the Profitable Client Pattern rules.

This is an OPERATIONAL signal for the dealing desk, not a compliance flag.
It identifies clients who are extracting money from the book at a
meaningful rate, with a statistically real edge, spread across many trades
and many days. The rule does not care which strategy the client uses
(scalping, fading, trend-following, news); it only cares that the client
is consistently profitable.

Sub-rules:
  R1: profit_extraction_rate >= 100      (USD per day net)
  R2: trade_count >= 50 AND profit_factor >= 1.2
  R3: biggest_single_win_share <= 0.30   (no one trade carries the P&L)
  R4: profitable_days_ratio >= 0.60      (>=60% of trading days positive)
"""

from __future__ import annotations

from . import metrics
from .types import RuleOutcome, insufficient


SUB_RULES = (
    "profit_extraction_rate >= 100",
    "trade_count >= 50 AND profit_factor >= 1.2",
    "biggest_single_win_share <= 0.30",
    "profitable_days_ratio >= 0.60",
)


def evaluate(snapshot) -> list[RuleOutcome]:
    out: list[RuleOutcome] = []

    # R1 — profit extraction rate
    rule = SUB_RULES[0]
    rate = metrics.total_profit_per_day(snapshot)
    if rate is None:
        out.append(insufficient(rule, "no trades or invalid window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(rate, 2),
                true=rate >= 100,
                reason=f"net profit of ${rate:.2f} per day",
            )
        )

    # R2 — statistically real edge (volume + profit factor)
    rule = SUB_RULES[1]
    count = metrics.trade_count(snapshot)
    pf = metrics.profit_factor(snapshot)
    if pf is None:
        out.append(insufficient(rule, "not enough trades on both sides to compute profit factor"))
    else:
        passes = count >= 50 and pf >= 1.2
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value={"trade_count": count, "profit_factor": round(pf, 4)},
                true=passes,
                reason=f"{count} trades, profit factor {pf:.2f}",
            )
        )

    # R3 — distributed winnings (no single trade dominates)
    rule = SUB_RULES[2]
    share = metrics.biggest_single_win_share(snapshot)
    if share is None:
        out.append(insufficient(rule, "no winning trades in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(share, 4),
                true=share <= 0.30,
                reason=f"biggest single win is {share:.1%} of total gross wins",
            )
        )

    # R4 — consistent winning across days
    rule = SUB_RULES[3]
    ratio = metrics.profitable_days_ratio(snapshot)
    if ratio is None:
        out.append(insufficient(rule, "fewer than 3 trading days in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(ratio, 4),
                true=ratio >= 0.60,
                reason=f"{ratio:.0%} of trading days ended profitable",
            )
        )

    return out
