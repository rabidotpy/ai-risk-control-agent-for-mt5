"""HTTP endpoints.

POST /analyse_risk    — Run analysis on the snapshots in the request envelope.
                        With `enqueue_and_callback=true` the call returns 202
                        and a background worker delivers the result via the
                        configured callback URL.
GET  /analyses        — Fetch stored evaluations for (mt5_login, window_start).
GET  /history         — Fetch stored behaviour summaries for an mt5_login.
GET  /runs/{run_id}   — Status of a single analysis run (queued/running/...).
GET  /healthz         — Liveness.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from ..config import settings
from ..models import AnalysisRun, RiskEvaluation, RiskHistorySummary
from ..schemas.analysis import AnalyseRiskRequest, EnqueuedJob, RiskFinding
from ..services import Job, analyse_snapshots, filter_high_risk_accounts
from .deps import CallbackDep, EvaluatorDep, get_job_queue


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/healthz", response_model=dict[str, str])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/analyse_risk",
    response_model=list[RiskFinding] | EnqueuedJob,
    responses={202: {"model": EnqueuedJob}},
)
async def analyse_risk(
    params: AnalyseRiskRequest,
    request: Request,
    response: Response,
    evaluator: EvaluatorDep,
    callback_fn: CallbackDep,
) -> list[RiskFinding] | EnqueuedJob:
    """Run risk analysis on the snapshots in the request envelope.

    Two execution modes:

    * `enqueue_and_callback=false` (default) — synchronous. The request
      blocks until every (snapshot × risk) is evaluated and persisted,
      then returns the findings list. The result is also POSTed to the
      configured callback URL.

    * `enqueue_and_callback=true` — async. The server creates an
      `AnalysisRun(status="queued")`, returns `202 Accepted` with the
      `run_id`, and a background worker performs the analysis and
      delivers the result to the callback URL when ready. The client
      may also poll `GET /runs/{run_id}` for status.

    Each finding row carries `mt5_login` and `behavior_summary` (the
    AI's rolling per-account summary).

    `include_history` (per-request) overrides `settings.include_history_default`.
    When False, prior summaries are not loaded into the prompt and not
    upserted afterwards — useful for replay / debug calls.
    """
    if not params.snapshots:
        logger.info("analyse_risk: empty snapshots, returning []")
        return []

    include_history = (
        params.include_history
        if params.include_history is not None
        else settings.include_history_default
    )
    trigger = params.snapshots[0].trigger_type

    if params.enqueue_and_callback:
        queue = get_job_queue(request)
        run = await AnalysisRun.create(
            trigger_type=trigger,
            snapshot_count=len(params.snapshots),
            status="queued",
        )
        await queue.enqueue(
            Job(
                run_id=run.id,
                snapshots=list(params.snapshots),
                include_history=include_history,
                trigger_type=trigger,
            )
        )
        response.status_code = status.HTTP_202_ACCEPTED
        logger.info(
            "analyse_risk: enqueued run_id=%s snapshots=%d trigger=%s",
            run.id,
            len(params.snapshots),
            trigger,
        )
        return EnqueuedJob(
            run_id=run.id,
            status="queued",
            poll_url=f"/runs/{run.id}",
            snapshot_count=len(params.snapshots),
        )

    logger.info(
        "analyse_risk: start snapshots=%d trigger=%s include_history=%s",
        len(params.snapshots),
        trigger,
        include_history,
    )
    run, findings = await analyse_snapshots(
        snapshots=params.snapshots,
        evaluator=evaluator,
        include_history=include_history,
        trigger_type=trigger,
    )

    # Forward only accounts whose max risk_score crosses the threshold.
    # Stored RiskEvaluation rows are unaffected — /analyses still shows
    # everything for audit purposes.
    outbound = filter_high_risk_accounts(
        findings, min_score=settings.callback_min_score
    )
    body = [f.model_dump(mode="json") for f in outbound]
    cb_status = await callback_fn(body)
    run.status = "completed"
    run.callback_status = cb_status
    run.finished_at = datetime.now(timezone.utc)
    await run.save()
    logger.info(
        "analyse_risk: done run_id=%s findings=%d forwarded=%d callback=%s",
        run.id,
        len(findings),
        len(outbound),
        cb_status.get("status"),
    )

    return outbound


@router.get("/runs/{run_id}", response_model=dict)
async def get_run(run_id: int) -> dict:
    """Status + result pointer for one analysis run.

    `status` is one of `queued`, `running`, `completed`, `failed`. When
    `completed`, fetch the actual findings from `/analyses`.
    """
    run = await AnalysisRun.get_or_none(id=run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "run_id": run_id},
        )
    return {
        "run_id": run.id,
        "status": run.status,
        "trigger_type": run.trigger_type,
        "snapshot_count": run.snapshot_count,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "callback_status": run.callback_status,
        "error": run.error,
    }


@router.get("/analyses", response_model=list[dict])
async def get_analyses(
    mt5_login: int = Query(...),
    window_start: datetime = Query(..., alias="start_time"),
) -> list[dict]:
    rows = await RiskEvaluation.filter(
        mt5_login=mt5_login, window_start=window_start
    ).order_by("risk_key")
    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "mt5_login": mt5_login,
                "start_time": window_start.isoformat(),
            },
        )
    return [
        {
            "mt5_login": r.mt5_login,
            "risk_type": r.risk_key,
            "risk_score": r.risk_score,
            "risk_level": r.risk_level,
            "trigger_type": r.trigger_type,
            "evidence": r.evidence,
            "suggested_action": r.suggested_action,
            "analysis": r.analysis,
            "behavior_summary": r.behavior_summary,
            "window_start": r.window_start.isoformat(),
            "window_end": r.window_end.isoformat(),
        }
        for r in rows
    ]


@router.get("/history", response_model=list[dict])
async def get_history(mt5_login: int = Query(...)) -> list[dict]:
    """Return the rolling behaviour summary per risk type for an mt5_login."""
    rows = await RiskHistorySummary.filter(mt5_login=mt5_login).order_by("risk_key")
    return [
        {
            "mt5_login": r.mt5_login,
            "risk_key": r.risk_key,
            "payload": r.payload,
            "run_count": r.run_count,
            "last_score": r.last_score,
            "last_level": r.last_level,
            "first_seen_at": r.first_seen_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]
