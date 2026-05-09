"""Historical context aggregation (Phase B).

Given the current 6h window for an account, the aggregator stretches the
lens by reading our local raw-pull cache (24h, 72h, 30d folds) and the
verdict-history collection (last N scan scores per risk_type).

The result is a small, JSON-serialisable dict the engine appends to the
LLM payload. Counters here power the *literal* PRD-window rules
(scalping R1 = 100 trades / 24h, bonus R2 = 30 trades / 24h after bonus,
bonus R5 = withdrawal within 72h of bonus). Verdict trend powers the
"repeat-offender" rule shared by all four risks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .. import config
from ..db import history as history_repo
from ..db import raw_pulls as raw_pulls_repo


# How far back each counter looks. All anchored at the *current scan's*
# end_time so re-runs of the same window produce identical context.
LOOKBACK_24H = timedelta(hours=24)
LOOKBACK_72H = timedelta(hours=72)
LOOKBACK_30D = timedelta(days=30)

TREND_LOOKBACK_LIMIT = 5  # last N scans per risk type used by the trend rule
TREND_HIGH_SCORE_THRESHOLD = 75  # "high" or "critical" → counts toward trend


# ---------------------------------------------------------------------------
# Per-account counters from the raw-pull cache
# ---------------------------------------------------------------------------


def _events_in_range(
    pulls: Iterable[dict[str, Any]],
    *,
    section: str,
    login: int,
    range_start: datetime,
    range_end: datetime,
    time_field: str = "time",
) -> list[dict[str, Any]]:
    """Flatten one event section across pulls, filter to login + range."""
    out: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    for pull in pulls:
        for ev in pull["envelope"]["data"].get(section, []):
            if ev.get("login") != login:
                continue
            ts_raw = ev.get(time_field)
            if not ts_raw:
                continue
            ts = _parse_iso(ts_raw)
            if ts is None or not (range_start <= ts <= range_end):
                continue
            ev_id = ev.get("id")
            if ev_id in seen_ids:
                # Same event present in two overlapping pulls — dedupe.
                continue
            seen_ids.add(ev_id)
            out.append(ev)
    return out


def _parse_iso(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _account_counters(
    *,
    raw_coll,
    login: int,
    window_end: datetime,
) -> dict[str, Any]:
    """Aggregated counters anchored at `window_end`, going back 30d."""

    range_start_30d = window_end - LOOKBACK_30D
    pulls = raw_pulls_repo.fetch_pulls_in_range(
        raw_coll,
        range_start=range_start_30d,
        range_end=window_end,
        login=login,
    )

    # Trades — closing time is the in-window anchor (matches schemas.bucket_by_login).
    trades_30d = _events_in_range(
        pulls,
        section="trades",
        login=login,
        range_start=range_start_30d,
        range_end=window_end,
        time_field="close_time",  # serialised field name; alias "time" is input-only
    )
    range_start_24h = window_end - LOOKBACK_24H
    trade_count_24h = sum(1 for t in trades_30d if _parse_iso(t["close_time"]) >= range_start_24h)

    # Bonus events.
    bonus_30d = _events_in_range(
        pulls,
        section="bonus",
        login=login,
        range_start=range_start_30d,
        range_end=window_end,
    )
    bonus_count_30d = len(bonus_30d)
    most_recent_bonus = max((_parse_iso(b["time"]) for b in bonus_30d), default=None)

    # Trades after the most recent bonus, within 24h of that bonus.
    trades_within_24h_after_bonus = 0
    if most_recent_bonus is not None:
        bonus_plus_24h = most_recent_bonus + LOOKBACK_24H
        trades_within_24h_after_bonus = sum(
            1
            for t in trades_30d
            if (ts := _parse_iso(t.get("open_time"))) is not None
            and most_recent_bonus <= ts <= bonus_plus_24h
        )

    # Withdrawals.
    withdraws_30d = _events_in_range(
        pulls,
        section="withdraws",
        login=login,
        range_start=range_start_30d,
        range_end=window_end,
    )
    # Earliest withdrawal at or after the most recent bonus, within 72h.
    withdrawal_within_72h_of_bonus = False
    hours_bonus_to_withdrawal: float | None = None
    if most_recent_bonus is not None:
        candidates = sorted(
            (
                _parse_iso(w["time"])
                for w in withdraws_30d
                if (_parse_iso(w["time"]) or datetime.max.replace(tzinfo=timezone.utc))
                >= most_recent_bonus
            )
        )
        if candidates:
            hours = (candidates[0] - most_recent_bonus).total_seconds() / 3600
            hours_bonus_to_withdrawal = round(hours, 2)
            withdrawal_within_72h_of_bonus = hours <= 72

    return {
        "trade_count_24h": trade_count_24h,
        "trade_count_30d": len(trades_30d),
        "bonus_count_30d": bonus_count_30d,
        "most_recent_bonus_time": most_recent_bonus.isoformat() if most_recent_bonus else None,
        "trades_within_24h_after_bonus": trades_within_24h_after_bonus,
        "withdrawal_within_72h_of_bonus": withdrawal_within_72h_of_bonus,
        "hours_bonus_to_withdrawal": hours_bonus_to_withdrawal,
        "raw_pulls_used": len(pulls),
    }


# ---------------------------------------------------------------------------
# Verdict trend
# ---------------------------------------------------------------------------


def _trend_for_risk(
    *,
    analyses_coll,
    login: int,
    risk_type: str,
    window_start: datetime,
) -> dict[str, Any]:
    """Last-N verdict scores for one risk type, oldest→newest in `prior_scores`."""

    rows = history_repo.get_recent_results(
        analyses_coll,
        mt5_login=login,
        risk_type=risk_type,
        before=window_start,
        limit=TREND_LOOKBACK_LIMIT,
    )
    rows.reverse()  # newest-first → oldest-first for human reading + the rule
    prior_scores = [int(r["risk_score"]) for r in rows]
    high_count = sum(1 for s in prior_scores if s >= TREND_HIGH_SCORE_THRESHOLD)
    return {
        "prior_scores": prior_scores,
        "prior_high_or_critical_count": high_count,
        "scans_observed": len(prior_scores),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_historical_context(
    *,
    mongo_client,
    mt5_login: int,
    window_start: datetime,
    window_end: datetime,
    risk_keys: tuple[str, ...],
) -> dict[str, Any]:
    """Build the `historical_context` block for a single account snapshot.

    Layout:
        {
            "lookbacks": {
                "trade_count_24h": ...,
                "trade_count_30d": ...,
                "bonus_count_30d": ...,
                "most_recent_bonus_time": iso | null,
                "trades_within_24h_after_bonus": ...,
                "withdrawal_within_72h_of_bonus": bool,
                "hours_bonus_to_withdrawal": float | null,
                "raw_pulls_used": int,
            },
            "trend_by_risk": {
                "<risk_key>": {
                    "prior_scores": [int, ...],
                    "prior_high_or_critical_count": int,
                    "scans_observed": int,
                },
                ...
            },
        }

    Both sub-objects are always present (possibly with empty / null fields)
    so the prompt schema is stable regardless of how much history exists.
    """
    raw_coll = mongo_client[config.MONGODB_DATABASE][config.RAW_PULLS_COLLECTION]
    analyses_coll = mongo_client[config.MONGODB_DATABASE][config.MONGODB_COLLECTION]

    lookbacks = _account_counters(
        raw_coll=raw_coll,
        login=mt5_login,
        window_end=window_end,
    )

    trend_by_risk = {
        rk: _trend_for_risk(
            analyses_coll=analyses_coll,
            login=mt5_login,
            risk_type=rk,
            window_start=window_start,
        )
        for rk in risk_keys
    }

    return {"lookbacks": lookbacks, "trend_by_risk": trend_by_risk}
