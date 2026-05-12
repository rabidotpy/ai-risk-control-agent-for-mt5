"""Account-level high-risk filter.

A pure function that drops findings for accounts whose maximum
per-risk score is below `min_score`. Used by both the synchronous
/analyse_risk response and the background-worker callback delivery.

Per-account, not per-row: if any of an account's risks is at or above
the threshold, every row for that account is forwarded — Alex sees the
full picture for actionable accounts.

Persistence is unaffected; this only filters what leaves the service.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from ..schemas import RiskFinding


logger = logging.getLogger(__name__)


def filter_high_risk_accounts(
    findings: list[RiskFinding], *, min_score: int
) -> list[RiskFinding]:
    """Drop entire accounts whose max risk_score is below `min_score`.

    Order is preserved.
    """
    if not findings:
        return findings

    max_by_login: dict[int, int] = defaultdict(int)
    for f in findings:
        if f.risk_score > max_by_login[f.mt5_login]:
            max_by_login[f.mt5_login] = f.risk_score

    keep = {
        login for login, score in max_by_login.items() if score >= min_score
    }
    dropped = set(max_by_login) - keep
    if dropped:
        logger.info(
            "filter_high_risk_accounts: kept=%d dropped=%d min_score=%d",
            len(keep),
            len(dropped),
            min_score,
        )

    return [f for f in findings if f.mt5_login in keep]
