"""Persistence operations on the risk_analyses collection.

Each scan stores N rows (one per risk type), keyed by
(mt5_login, start_time, risk_type). On re-runs the existing rows are
overwritten — latest analysis wins. This is the contract Rabi specified:
"if the data is already present in database, it gets overwritten with
fresh data."

Reads return a list of plain dicts that the API layer hands back to the
client unchanged (after stripping Mongo's `_id`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..schemas import RiskResult


def get_results(
    coll,
    *,
    mt5_login: int,
    start_time: datetime,
) -> list[dict[str, Any]]:
    """Return the cached rows for one scan, or [] if no rows exist yet.

    Rows are sorted by `risk_type` for deterministic output.
    """
    cursor = coll.find(
        {"mt5_login": mt5_login, "start_time": start_time},
        projection={"_id": False},
    ).sort("risk_type", 1)
    return list(cursor)


def has_results(coll, *, mt5_login: int, start_time: datetime) -> bool:
    return (
        coll.count_documents(
            {"mt5_login": mt5_login, "start_time": start_time}, limit=1
        )
        > 0
    )


def save_results(
    coll,
    *,
    mt5_login: int,
    start_time: datetime,
    end_time: datetime,
    results: list[RiskResult],
) -> None:
    """Upsert one row per risk result.

    Re-runs overwrite: if a row already exists for
    (mt5_login, start_time, risk_type), it's replaced with the fresh one.
    Each row carries `start_time` / `end_time` / `created_at` for audit.
    """
    now = datetime.now(tz=timezone.utc)
    for r in results:
        doc = r.model_dump()
        doc.update(
            {
                "start_time": start_time,
                "end_time": end_time,
                "created_at": now,
            }
        )
        key = {
            "mt5_login": r.mt5_login,
            "start_time": start_time,
            "risk_type": r.risk_type,
        }
        # `replace_one` with upsert=True is atomic per document and
        # respects the unique compound index on (mt5_login, start_time,
        # risk_type). If a row exists at this key, it's replaced. If not,
        # the doc is inserted.
        coll.replace_one(key, doc, upsert=True)
