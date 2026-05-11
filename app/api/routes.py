"""HTTP endpoints.

POST /analyse_risk    — Run analysis on the snapshots in the request envelope.
GET  /analyses        — Fetch stored evaluations for (mt5_login, window_start).
GET  /history         — Fetch stored behaviour summaries for an mt5_login.
GET  /healthz         — Liveness.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..models import RiskEvaluation, RiskHistorySummary
from ..schemas.analysis import AnalyseRiskRequest, RiskFinding
from ..services import analyse_snapshots
from .deps import CallbackDep, EvaluatorDep


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/healthz", response_model=dict[str, str])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyse_risk", response_model=list[RiskFinding])
async def analyse_risk(
    params: AnalyseRiskRequest,
    evaluator: EvaluatorDep,
    callback_fn: CallbackDep,
) -> list[RiskFinding]:
    """Run risk analysis on the snapshots in the request envelope.

    Each row in the response carries `mt5_login` and `behavior_summary`
    (the AI's rolling per-account summary).

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

    body = [f.model_dump(mode="json") for f in findings]
    cb_status = await callback_fn(body)
    run.callback_status = cb_status
    run.finished_at = datetime.now(timezone.utc)
    await run.save()
    logger.info(
        "analyse_risk: done run_id=%s findings=%d callback=%s",
        run.id,
        len(findings),
        cb_status.get("status"),
    )

    return findings


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
