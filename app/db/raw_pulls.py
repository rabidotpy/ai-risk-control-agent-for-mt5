"""Raw Alex-pull cache (Phase B).

Each scheduled scan stores its 6h Alex envelope here verbatim. The cache
exists ONLY so the aggregator can reconstruct rolling windows longer than
6h (24h, 72h, 30d) without re-pulling. We are not the system of record
for raw broker events — Alex is. Rows expire automatically via a TTL
index on `pulled_at`, capped at `RAW_PULL_TTL_DAYS` (default 35d, just
over the longest aggregation window).

Document shape:
    {
        "start_time":  datetime,        # the 6h window start (UTC)
        "end_time":    datetime,        # the 6h window end   (UTC)
        "pulled_at":   datetime,        # when we stored it (TTL anchor)
        "logins":      [int, ...],      # quick filter for per-account fetch
        "envelope":    {                # raw AlexResponse JSON
            "status": bool,
            "start_time": iso,
            "end_time":   iso,
            "data": { deposits, withdraws, trades, bonus, linked_accounts },
        },
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING

from .. import config
from ..schemas import AlexResponse


def get_collection(client) -> Any:
    return client[config.MONGODB_DATABASE][config.RAW_PULLS_COLLECTION]


def ensure_indexes(coll) -> None:
    """Create raw-pull indexes. Idempotent — safe on every boot.

    `pulled_at` carries the TTL so the cache self-trims; even if the
    scheduler is paused or a backfill writes old pulls, nothing grows
    unboundedly.
    """
    # Lookup by window — used by aggregator to fetch the slice of pulls
    # covering [t - N hours, t] in chronological order.
    coll.create_index(
        [("start_time", ASCENDING)],
        name="raw_by_start_time",
    )
    # Per-login filtering when an account-level aggregation only needs the
    # subset of pulls that mention this login.
    coll.create_index([("logins", ASCENDING)], name="raw_by_login")
    # TTL on pulled_at — auto-expire after RAW_PULL_TTL_DAYS.
    coll.create_index(
        [("pulled_at", ASCENDING)],
        name="raw_ttl",
        expireAfterSeconds=config.RAW_PULL_TTL_DAYS * 24 * 3600,
    )
    # Replays of the same window overwrite (one row per (start_time, end_time)).
    coll.create_index(
        [("start_time", ASCENDING), ("end_time", ASCENDING)],
        unique=True,
        name="raw_uniq_window",
    )


def save_pull(coll, *, envelope: AlexResponse) -> None:
    """Upsert the raw pull keyed by (start_time, end_time).

    Re-pulling the same window overwrites — same contract as risk_analyses.
    """
    payload = envelope.model_dump(mode="json")
    logins = sorted({
        *(d["login"] for d in payload["data"].get("deposits", [])),
        *(w["login"] for w in payload["data"].get("withdraws", [])),
        *(t["login"] for t in payload["data"].get("trades", [])),
        *(b["login"] for b in payload["data"].get("bonus", [])),
    })
    doc = {
        "start_time": envelope.start_time,
        "end_time": envelope.end_time,
        "pulled_at": datetime.now(tz=timezone.utc),
        "logins": logins,
        "envelope": payload,
    }
    coll.replace_one(
        {"start_time": envelope.start_time, "end_time": envelope.end_time},
        doc,
        upsert=True,
    )


def fetch_pulls_in_range(
    coll,
    *,
    range_start: datetime,
    range_end: datetime,
    login: int | None = None,
) -> list[dict[str, Any]]:
    """Return raw-pull docs whose 6h window overlaps `[range_start, range_end]`.

    A pull's window `[s, e]` overlaps iff `s <= range_end` and `e >= range_start`.
    Sorted oldest→newest by start_time so callers iterate in time order.

    `login` (optional) restricts to pulls that touched that account at all.
    """
    query: dict[str, Any] = {
        "start_time": {"$lte": range_end},
        "end_time": {"$gte": range_start},
    }
    if login is not None:
        query["logins"] = login

    return list(
        coll.find(query, projection={"_id": False}).sort("start_time", ASCENDING)
    )
