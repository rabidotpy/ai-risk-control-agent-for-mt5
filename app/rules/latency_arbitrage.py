"""Deterministic evaluation of the Latency Arbitrage rules.

Rule set, fixed:
  R1: trade_count_in_window >= 30
  R2: median_holding_time_seconds <= 30
  R3: minority_side_ratio >= 0.2
  R4: win_rate_high_no_batch_close   (win_rate >= 0.9 AND batch_close_ratio <= 0.2)

R3 and R4 are the cross-trade signals that distinguish real latency arbitrage
(both sides traded, near-100% wins, one-at-a-time closes) from the
martingale-grid false positive (one-sided, scattered losses, batch closes).
"""

from __future__ import annotations

from . import metrics
from .types import RuleOutcome, insufficient


SUB_RULES = (
    "trade_count_in_window >= 30",
    "median_holding_time_seconds <= 30",
    "minority_side_ratio >= 0.2",
    "win_rate >= 0.9 AND batch_close_ratio <= 0.2",
)


def evaluate(snapshot) -> list[RuleOutcome]:
    out: list[RuleOutcome] = []

    # R1
    count = metrics.trade_count(snapshot)
    out.append(
        RuleOutcome(
            rule=SUB_RULES[0],
            observed_value=count,
            true=count >= 30,
            reason=f"{count} closed positions in window",
        )
    )

    # R2
    rule = SUB_RULES[1]
    med = metrics.median_holding_seconds(snapshot)
    if med is None:
        out.append(insufficient(rule, "no trades in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(med, 4),
                true=med <= 30,
                reason=f"median holding time {med:.1f}s",
            )
        )

    # R3
    rule = SUB_RULES[2]
    minority = metrics.minority_side_ratio(snapshot)
    if minority is None:
        out.append(insufficient(rule, "no trades in window"))
    else:
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value=round(minority, 4),
                true=minority >= 0.2,
                reason=f"minority side {minority:.2%} of trades",
            )
        )

    # R4
    rule = SUB_RULES[3]
    if len(snapshot.trades) < 5:
        out.append(insufficient(rule, "fewer than 5 trades — win rate not meaningful"))
    else:
        wr = metrics.win_rate(snapshot) or 0.0
        bcr = metrics.batch_close_ratio(snapshot) or 0.0
        passes = wr >= 0.9 and bcr <= 0.2
        out.append(
            RuleOutcome(
                rule=rule,
                observed_value={"win_rate": round(wr, 4), "batch_close_ratio": round(bcr, 4)},
                true=passes,
                reason=(
                    f"win_rate {wr:.2%}, batch_close_ratio {bcr:.2%}"
                ),
            )
        )

    return out
