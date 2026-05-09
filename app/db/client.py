"""MongoDB connection helpers and index setup.

Tests inject a `mongomock.MongoClient`; production uses pymongo's real
client. Both follow the same MongoClient API, so this module never has to
branch on which one it's holding.
"""

from __future__ import annotations

from typing import Protocol

from pymongo import ASCENDING

from .. import config


class MongoLike(Protocol):
    """Minimal MongoClient surface we depend on."""

    def __getitem__(self, name: str): ...


def get_collection(client: MongoLike):
    """Return the configured collection from the given client."""
    return client[config.MONGODB_DATABASE][config.MONGODB_COLLECTION]


def ensure_indexes(coll) -> None:
    """Create the indexes we rely on. Idempotent — safe to call on every boot."""

    # Primary lookup + uniqueness on (mt5_login, start_time, risk_type).
    coll.create_index(
        [
            ("mt5_login", ASCENDING),
            ("start_time", ASCENDING),
            ("risk_type", ASCENDING),
        ],
        unique=True,
        name="uniq_login_starttime_risktype",
    )

    # Risk-type queries (e.g. "all latency_arbitrage cases above score 75").
    coll.create_index([("risk_type", ASCENDING)], name="by_risk_type")

    # Per-account history.
    coll.create_index(
        [("mt5_login", ASCENDING), ("start_time", ASCENDING)],
        name="by_login_starttime",
    )
