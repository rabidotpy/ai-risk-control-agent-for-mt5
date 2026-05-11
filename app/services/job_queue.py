"""In-process async job queue + worker pool.

Backs the `enqueue_and_callback=true` path on POST /analyse_risk:

  * The route creates an `AnalysisRun(status="queued")`, pushes a job
    into the queue, and returns 202 to the client.
  * `JobWorker` tasks pull jobs, run `analyse_snapshots`, deliver the
    result via the configured callback, and update the run row to
    `completed` (or `failed` with an error message).

This is intentionally an in-process queue (asyncio.Queue + worker tasks
in the same FastAPI process). It is NOT durable across restarts. If the
process dies before a queued job runs, the run row stays in `queued`
forever and must be retried by the client. For a durable queue, swap
this module for a Redis / SQS-backed implementation behind the same
`enqueue_job` / `start_workers` surface.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from ..config import settings
from ..llm import LLMEvaluator
from ..models import AnalysisRun
from ..schemas import AccountSnapshot
from .analysis import analyse_snapshot
from .callback import deliver as default_deliver


logger = logging.getLogger(__name__)


CallbackFn = Callable[[list[dict]], Awaitable[dict]]


@dataclass
class Job:
    run_id: int
    snapshots: list[AccountSnapshot]
    include_history: bool
    trigger_type: str


class JobQueue:
    """Tiny wrapper around `asyncio.Queue` plus a worker task pool."""

    def __init__(
        self,
        *,
        evaluator_provider: Callable[[], LLMEvaluator],
        callback_fn: CallbackFn,
        concurrency: int = 1,
        max_size: int = 1000,
    ) -> None:
        self._evaluator_provider = evaluator_provider
        self._callback_fn = callback_fn
        self._concurrency = max(0, concurrency)
        self._queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=max_size)
        self._workers: list[asyncio.Task] = []
        self._started = False

    @property
    def enabled(self) -> bool:
        return self._concurrency > 0

    @property
    def started(self) -> bool:
        return self._started

    async def enqueue(self, job: Job) -> None:
        if not self.enabled:
            raise RuntimeError("job worker disabled (JOB_WORKER_CONCURRENCY=0)")
        await self._queue.put(job)
        logger.info(
            "job enqueued run_id=%s snapshots=%d depth=%d",
            job.run_id,
            len(job.snapshots),
            self._queue.qsize(),
        )

    async def start(self) -> None:
        if self._started or not self.enabled:
            return
        for i in range(self._concurrency):
            self._workers.append(asyncio.create_task(self._worker_loop(i)))
        self._started = True
        logger.info("job workers started count=%d", self._concurrency)

    async def stop(self) -> None:
        if not self._started:
            return
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            try:
                await w
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._workers.clear()
        self._started = False
        logger.info("job workers stopped")

    async def _worker_loop(self, idx: int) -> None:
        logger.info("job worker %d ready", idx)
        while True:
            job = await self._queue.get()
            try:
                await self._run_job(job)
            except Exception:  # noqa: BLE001
                logger.exception("worker %d crashed on run_id=%s", idx, job.run_id)
            finally:
                self._queue.task_done()

    async def _run_job(self, job: Job) -> None:
        run = await AnalysisRun.get_or_none(id=job.run_id)
        if run is None:
            logger.error("worker: run_id=%s not found", job.run_id)
            return

        run.status = "running"
        await run.save()
        logger.info("job running run_id=%s", job.run_id)

        evaluator = self._evaluator_provider()
        try:
            findings: list = []
            for snapshot in job.snapshots:
                snapshot_findings = await analyse_snapshot(
                    snapshot=snapshot,
                    evaluator=evaluator,
                    run=run,
                    include_history=job.include_history,
                )
                findings.extend(snapshot_findings)

            body = [f.model_dump(mode="json") for f in findings]
            cb_status = await self._callback_fn(body)
            run.status = "completed"
            run.callback_status = cb_status
            run.finished_at = datetime.now(timezone.utc)
            await run.save()
            logger.info(
                "job completed run_id=%s findings=%d callback=%s",
                job.run_id,
                len(findings),
                cb_status.get("status"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("job failed run_id=%s", job.run_id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            await run.save()


def build_default_queue(
    *,
    evaluator_provider: Callable[[], LLMEvaluator],
    callback_fn: CallbackFn | None = None,
) -> JobQueue:
    """Wire a queue from settings. Used by app.main lifespan."""
    return JobQueue(
        evaluator_provider=evaluator_provider,
        callback_fn=callback_fn or default_deliver,
        concurrency=settings.job_worker_concurrency,
        max_size=settings.job_queue_max_size,
    )
