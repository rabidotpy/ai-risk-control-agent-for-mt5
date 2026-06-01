"""Profitable Client Pattern.

This risk type is operationally different from the other four. It is NOT
a compliance signal. It is a dealing-desk signal: identify clients who
are consistently extracting money from the book so the broker can decide
whether to route them to A-book (lay off the risk to a liquidity provider)
instead of carrying the position internally.

The 4 sub-rules are strategy-agnostic. They do not care whether the
client is scalping, fading, trend-following, or trading the news. They
only care that the client is profitable enough, consistently enough, and
the edge is statistically real (not luck).
"""

from __future__ import annotations

from ..rules import profitable_client_pattern as _eval
from .base import Risk


SUB_RULES = _eval.SUB_RULES


_RISK_PROMPT = """\
RISK BEING EVALUATED: Profitable Client Pattern

IMPORTANT: this is NOT a compliance alert. It is an OPERATIONAL signal
for the dealing desk. When this rule fires, the client is consistently
taking money from the broker's book at a meaningful rate. The broker is
not being cheated; the broker is just on the wrong side of a skilled
client. The appropriate response is to route the client's flow to
A-book (lay it off to a liquidity provider), not to restrict the
account.

The rule is deliberately strategy-agnostic. It does not care whether
the client is a discretionary scalper, a trend-follower, a news trader,
or anything else. It only asks four questions about the OUTCOMES, not
the recipes.

The rule engine has already decided these 4 rules for this window. Use
`rule_outcomes` to narrate; do not re-evaluate.

R1: profit_extraction_rate >= 100
   Net profit per day in the window, in USD. The threshold of $100/day
   is equivalent to $1,000 over 10 days. Below this, the client is not
   extracting enough to warrant the broker's attention.

R2: trade_count >= 50 AND profit_factor >= 1.2
   Profit Factor = gross wins / absolute value of gross losses. A PF of
   1.0 is breakeven; 1.2 or above is a real edge in retail trading.
   Combined with 50+ trades, this separates real skill from a lucky
   short streak.

R3: biggest_single_win_share <= 0.30
   The largest single winning trade's share of total gross wins. If one
   trade carries more than 30% of all winnings, the edge is suspect
   (could be one lucky pick). A spread-out share indicates a real
   repeatable pattern.

R4: profitable_days_ratio >= 0.60
   Fraction of trading days that ended profitable. At least 60% means
   the client is consistently winning across days, not just on one
   lucky session. Requires at least 3 distinct trading days in the
   window to be meaningful.

When narrating, frame this for the broker's risk officer as "this is
a profitable client" not "this is an abuser". The suggested_action
field will be a compliance string ("restrict_opening_pause_withdrawal"
etc.) for shared-tooling reasons; the dealing desk should read it as
"route this client to A-book" regardless of what the string says.
"""


PROFITABLE_CLIENT_PATTERN = Risk(
    name="Profitable Client Pattern",
    key="profitable_client_pattern",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
    evaluator=_eval.evaluate,
)
