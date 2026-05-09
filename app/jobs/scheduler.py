"""APScheduler wiring for the 6-hourly scan tick.

Disabled by default. Production entrypoint:

    SCHEDULER_ENABLED=true python -m app.jobs.scheduler

Tests never start the scheduler; they call `run_scan` directly.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pymongo import MongoClient

from .. import config
from ..llm import AnthropicEvaluator
from .scan_job import run_scan

logger = logging.getLogger(__name__)


def build_scheduler(
    *,
    mongo_client_factory: Callable[[], MongoClient] | None = None,
    evaluator_factory: Callable[[], object] | None = None,
) -> BackgroundScheduler:
    """Construct an APScheduler with the scan tick wired in.

    Factories are injected so a long-lived process owns its own resources
    (don't share Mongo clients across processes / forks).
    """
    sched = BackgroundScheduler(timezone="UTC")

    mongo_factory = mongo_client_factory or (lambda: MongoClient(config.MONGODB_URI))
    eval_factory = evaluator_factory or AnthropicEvaluator

    def _tick() -> None:
        # Build resources fresh each tick — keeps the scheduler resilient
        # to dropped Mongo connections and pooled-client weirdness.
        mongo = mongo_factory()
        try:
            evaluator = eval_factory()
            summary = run_scan(mongo_client=mongo, evaluator=evaluator)
            logger.info("scan tick complete: %s", summary.to_dict())
        finally:
            try:
                mongo.close()
            except Exception:  # noqa: BLE001
                logger.exception("mongo client close failed in scan tick")

    trigger = CronTrigger.from_crontab(f"0 {config.SCHEDULER_HOURS} * * *")
    sched.add_job(
        _tick,
        trigger=trigger,
        id="scan_tick",
        max_instances=1,           # don't pile up if a tick runs long
        coalesce=True,             # missed ticks fold into one
        misfire_grace_time=15 * 60,
    )
    return sched


def start_scheduler() -> BackgroundScheduler:
    """Build, start, and install signal handlers so the process exits cleanly."""
    sched = build_scheduler()
    sched.start()
    logger.info(
        "scheduler started: cron='0 %s * * *' (UTC)", config.SCHEDULER_HOURS
    )

    def _shutdown(signum, _frame):
        logger.info("received signal %s, shutting down scheduler", signum)
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    return sched


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.SCHEDULER_ENABLED:
        logger.warning("SCHEDULER_ENABLED is false; refusing to start. Set SCHEDULER_ENABLED=true.")
        sys.exit(1)
    start_scheduler()
    # Block forever — APScheduler runs in a background thread.
    while True:
        time.sleep(3600)
