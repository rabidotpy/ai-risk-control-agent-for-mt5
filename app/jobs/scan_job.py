"""End-to-end scan: pull → cache → bucket → aggregate → analyse → persist → callback.

The job is the single source of truth for what one "scan tick" does. The
scheduler calls it on a cron, and `POST /run_scan` calls it on demand;
both paths share identical behaviour.

Failures are scoped:
  * Alex fetch failure aborts the scan (nothing to analyse).
  * A single account's pipeline failure is logged and skipped — the
    remaining accounts still get analysed.
  * Callback failures never propagate; they are logged.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .. import callback as default_callback
from .. import engine
from ..db import client as db_client
from ..db import raw_pulls as raw_pulls_repo
from ..db import repo as db_repo
from ..history.aggregator import build_historical_context
from ..ingest.alex_client import AlexClient, AlexFetchError, get_default_client
from ..llm import LLMEvaluator
from ..risks import ALL_RISKS
from ..schemas import AlexResponse, TriggerType, bucket_by_login

logger = logging.getLogger(__name__)


# Risk keys passed to build_historical_context — derived once.
_RISK_KEYS: tuple[str, ...] = tuple(r.key for r in ALL_RISKS)


@dataclass
class ScanResult:
    """Summary of one scan tick. Returned by run_scan; logged by the scheduler."""

    start_time: datetime
    end_time: datetime
    accounts_analysed: int = 0
    accounts_failed: int = 0
    results_persisted: int = 0
    error: str | None = None
    failed_logins: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "accounts_analysed": self.accounts_analysed,
            "accounts_failed": self.accounts_failed,
            "results_persisted": self.results_persisted,
            "error": self.error,
            "failed_logins": list(self.failed_logins),
        }


# ---------------------------------------------------------------------------
# Window math
# ---------------------------------------------------------------------------


def latest_completed_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the most recently completed 6h window aligned to 00/06/12/18 UTC.

    Window end is `start + 6h - 1ms` to match the convention used elsewhere
    (matches the (start_time, end_time) uniqueness key on raw_pulls).
    """
    now = now or datetime.now(tz=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    aligned_hour = (now.hour // 6) * 6
    candidate_start = now.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
    candidate_end = candidate_start + timedelta(hours=6) - timedelta(milliseconds=1)
    if candidate_end > now:
        # Current window hasn't closed yet — go back one slot.
        candidate_start -= timedelta(hours=6)
        candidate_end = candidate_start + timedelta(hours=6) - timedelta(milliseconds=1)
    return candidate_start, candidate_end


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_scan(
    *,
    mongo_client,
    evaluator: LLMEvaluator,
    alex_client: AlexClient | None = None,
    callback_fn: Callable[[list], dict] | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    trigger_type: TriggerType = "scheduled_scan",
    deliver_callback_blocking: bool = False,
) -> ScanResult:
    """Run one full scan cycle. Pure-function in/out — no globals touched.

    Args mirror the scheduler/handler boundary so tests can inject any combo.
    `start_time` / `end_time` default to the latest completed 6h window.
    """
    alex = alex_client or get_default_client()
    cb_fn = callback_fn or default_callback.deliver

    if start_time is None or end_time is None:
        start_time, end_time = latest_completed_window()

    summary = ScanResult(start_time=start_time, end_time=end_time)

    # 1) Fetch from Alex
    try:
        envelope: AlexResponse = alex.fetch_window(start_time=start_time, end_time=end_time)
    except AlexFetchError as e:
        logger.error("alex fetch failed for window %s..%s: %s", start_time, end_time, e)
        summary.error = f"alex_fetch_failed: {e}"
        return summary

    # 2) Cache the raw pull (TTL-bounded). Failures here are non-fatal;
    #    we still analyse the in-memory envelope.
    raw_coll = raw_pulls_repo.get_collection(mongo_client)
    try:
        raw_pulls_repo.ensure_indexes(raw_coll)
        raw_pulls_repo.save_pull(raw_coll, envelope=envelope)
    except Exception:  # noqa: BLE001
        logger.exception("raw_pulls cache write failed; proceeding with analysis")

    # 3) Bucket by login.
    snapshots = bucket_by_login(envelope, trigger_type=trigger_type)
    if not snapshots:
        logger.info("scan window %s..%s produced no per-account snapshots", start_time, end_time)
        return summary

    # 4) Per account: build historical context, analyse, persist, callback.
    analyses_coll = db_client.get_collection(mongo_client)
    db_client.ensure_indexes(analyses_coll)

    all_results_for_callback: list[dict[str, Any]] = []

    for snapshot in snapshots:
        try:
            historical_context = build_historical_context(
                mongo_client=mongo_client,
                mt5_login=snapshot.mt5_login,
                window_start=snapshot.start_time,
                window_end=snapshot.end_time,
                risk_keys=_RISK_KEYS,
            )
            results = engine.analyse(
                snapshot,
                evaluator,
                historical_context=historical_context,
            )
            db_repo.save_results(
                analyses_coll,
                mt5_login=snapshot.mt5_login,
                start_time=snapshot.start_time,
                end_time=snapshot.end_time,
                results=results,
            )
            summary.accounts_analysed += 1
            summary.results_persisted += len(results)
            all_results_for_callback.extend(r.model_dump(mode="json") for r in results)
        except Exception:  # noqa: BLE001 — isolate per-account failure
            logger.exception(
                "scan: per-account pipeline failed for login=%s",
                snapshot.mt5_login,
            )
            summary.accounts_failed += 1
            summary.failed_logins.append(snapshot.mt5_login)

    # 5) Callback once with the full batch (PRD §5.3 — broker prefers a
    #    single delivery per scan tick, not one per account).
    if all_results_for_callback:
        _deliver_callback(cb_fn, all_results_for_callback, blocking=deliver_callback_blocking)

    return summary


# ---------------------------------------------------------------------------
# Callback dispatch — mirrors api._dispatch_callback semantics so behaviour
# is consistent across HTTP and scheduler paths.
# ---------------------------------------------------------------------------


def _deliver_callback(callback_fn: Callable[[list], dict], body: list, *, blocking: bool) -> None:
    if blocking:
        try:
            callback_fn(body)
        except Exception:  # noqa: BLE001
            logger.exception("scan callback raised")
        return

    def _run() -> None:
        try:
            callback_fn(body)
        except Exception:  # noqa: BLE001
            logger.exception("scan callback raised in background thread")

    threading.Thread(target=_run, name="scan-callback", daemon=True).start()
