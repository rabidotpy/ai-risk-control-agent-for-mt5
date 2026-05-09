"""Verdict-history reads (Phase B).

Reads from the `risk_analyses` collection (the same one repo.py writes
to). This is the *trend* signal — we look at past verdicts for an
account so the LLM can factor "repeat offender" into the current scan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import DESCENDING


def get_recent_results(
    coll,
    *,
    mt5_login: int,
    risk_type: str,
    before: datetime,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the latest `limit` verdicts for (mt5_login, risk_type) strictly
    BEFORE `before` (the current scan's start_time), newest first.

    Sorted newest→oldest so callers can show "last N" without re-sorting;
    the aggregator then trims to whatever it needs.
    """
    cursor = (
        coll.find(
            {
                "mt5_login": mt5_login,
                "risk_type": risk_type,
                "start_time": {"$lt": before},
            },
            projection={
                "_id": False,
                "risk_score": True,
                "risk_level": True,
                "start_time": True,
                "end_time": True,
            },
        )
        .sort("start_time", DESCENDING)
        .limit(limit)
    )
    return list(cursor)
