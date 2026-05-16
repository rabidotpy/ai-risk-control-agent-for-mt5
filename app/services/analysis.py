"""Analysis orchestrator.

For each (snapshot, risk):
  1. Load `prior_behavior_summary` from `RiskHistorySummary` (if include_history).
  2. Run the deterministic rule engine — this decides per-rule TRUE/FALSE
     and the score. It is the source of truth.
  3. Build the user payload (current_window + rule_outcomes + prior_summary).
  4. Call the LLM to obtain `summary` + `behavior_summary` only (and an
     optional `notable_patterns` advisory). If it fails, the finding
     still has the deterministic score; only the narrative becomes a
     templated fallback string.
  5. Persist `RiskEvaluation` row (audit trail).
  6. Upsert `RiskHistorySummary.payload` with the AI's new behaviour summary
     (if include_history).

A single failing risk does NOT lose the other risks for the same account:
the per-risk loop catches and records a finding with the deterministic
score and an error-marker analysis text instead.
"""

from __future__ import annotations

import logging
from typing import Any

from tortoise.transactions import in_transaction

from ..config import settings
from ..llm import LLMEvaluator, build_user_payload
from ..models import AnalysisRun, RiskEvaluation, RiskHistorySummary
from ..risks import ALL_RISKS, Risk
from ..rules import RuleOutcome
from ..schemas import AccountSnapshot, RiskFinding
from .prescreen import prescreen_snapshot
from .scoring import compute_score, level_to_action, score_to_level


logger = logging.getLogger(__name__)


_COMPARISON_OPS = (" >= ", " <= ", " > ", " < ", " == ")


def _metric_name(rule: str) -> str:
    """Strip the comparison + threshold from a rule string."""
    for op in _COMPARISON_OPS:
        if op in rule:
            return rule.split(op, 1)[0]
    return rule


def _build_evidence(outcomes: list[RuleOutcome]) -> dict[str, Any]:
    """Surface observed_value per rule, keyed by metric name."""
    out: dict[str, Any] = {}
    for o in outcomes:
        if o.observed_value is None:
            continue
        out[_metric_name(o.rule)] = o.observed_value
    return out


def _count_true_sub_rules(outcomes: list[RuleOutcome]) -> int:
    """Count sub-rules the rule engine marked true, deduped by rule text."""
    seen: set[str] = set()
    for o in outcomes:
        if o.true and o.rule not in seen:
            seen.add(o.rule)
    return len(seen)


def _fallback_summary(risk: Risk, outcomes: list[RuleOutcome]) -> str:
    """Templated narrative used when the LLM call fails."""
    fired = [o for o in outcomes if o.true]
    if not fired:
        return f"no {risk.name} rules fired in window"
    parts = ", ".join(f"{o.rule} ({o.reason})" for o in fired)
    return f"{risk.name}: {parts}"


async def _load_prior_summary(
    *, mt5_login: int, risk_key: str
) -> RiskHistorySummary | None:
    return await RiskHistorySummary.get_or_none(
        mt5_login=mt5_login, risk_key=risk_key
    )


async def _upsert_summary(
    *,
    mt5_login: int,
    risk_key: str,
    payload: dict[str, Any],
    score: int,
    level: str,
) -> None:
    """Insert or update the rolling summary for this (login, risk_key)."""
    existing = await RiskHistorySummary.get_or_none(
        mt5_login=mt5_login, risk_key=risk_key
    )
    if existing is None:
        await RiskHistorySummary.create(
            mt5_login=mt5_login,
            risk_key=risk_key,
            payload=payload,
            run_count=1,
            last_score=score,
            last_level=level,
        )
        return
    existing.payload = payload
    existing.run_count += 1
    existing.last_score = score
    existing.last_level = level
    await existing.save()


def _build_skipped_finding(
    *, risk: Risk, snapshot: AccountSnapshot
) -> RiskFinding:
    """Synthetic zero-score finding for a risk that failed prescreen."""
    return RiskFinding(
        mt5_login=snapshot.mt5_login,
        risk_type=risk.key,
        risk_score=0,
        risk_level="low",
        trigger_type=snapshot.trigger_type,
        evidence={"prescreen": "skipped: no rule could plausibly trip"},
        suggested_action=level_to_action("low"),
        analysis="prescreen: skipped LLM evaluation (no rule could trip)",
        behavior_summary=None,
    )


async def _evaluate_one(
    *,
    risk: Risk,
    snapshot: AccountSnapshot,
    evaluator: LLMEvaluator,
    include_history: bool,
) -> tuple[RiskFinding, dict[str, Any] | None]:
    """Returns (finding, behavior_summary_payload | None)."""
    outcomes = list(risk.evaluator(snapshot))
    num_true = _count_true_sub_rules(outcomes)
    score = compute_score(risk.num_sub_rules, num_true)
    level = score_to_level(score)
    evidence = _build_evidence(outcomes)

    prior_obj = (
        await _load_prior_summary(mt5_login=snapshot.mt5_login, risk_key=risk.key)
        if include_history
        else None
    )
    prior_payload = prior_obj.payload if prior_obj is not None else None

    summary_text = _fallback_summary(risk, outcomes)
    behavior_summary: dict[str, Any] | None = None
    notable_patterns: str | None = None

    # Gate the LLM narration on the deterministic score. Low-scoring risks
    # get a templated one-line summary; the rule engine has already produced
    # the verdict that matters for the audit trail and the outbound filter.
    if score < settings.llm_narrate_min_score:
        logger.debug(
            "LLM narration skipped login=%s risk=%s score=%d < %d",
            snapshot.mt5_login,
            risk.key,
            score,
            settings.llm_narrate_min_score,
        )
    else:
        payload_json = build_user_payload(
            snapshot, prior_payload, rule_outcomes=outcomes
        )
        try:
            tool_input = await evaluator.evaluate(risk, payload_json)
        except Exception as exc:  # noqa: BLE001 — contain per-risk failure
            logger.exception(
                "LLM narration failed for login=%s risk=%s (score still computed)",
                snapshot.mt5_login,
                risk.key,
            )
            summary_text = (
                f"{_fallback_summary(risk, outcomes)} "
                f"[LLM narration unavailable: {type(exc).__name__}]"
            )
        else:
            text = tool_input.get("summary")
            if isinstance(text, str) and text.strip():
                summary_text = text
            bs = tool_input.get("behavior_summary")
            if isinstance(bs, dict):
                behavior_summary = bs
            np_field = tool_input.get("notable_patterns")
            if isinstance(np_field, str) and np_field.strip():
                notable_patterns = np_field

    if notable_patterns:
        evidence = {**evidence, "notable_patterns": notable_patterns}

    finding = RiskFinding(
        mt5_login=snapshot.mt5_login,
        risk_type=risk.key,
        risk_score=score,
        risk_level=level,
        trigger_type=snapshot.trigger_type,
        evidence=evidence,
        suggested_action=level_to_action(level),
        analysis=summary_text,
        behavior_summary=behavior_summary,
    )
    return finding, behavior_summary


async def analyse_snapshot(
    *,
    snapshot: AccountSnapshot,
    evaluator: LLMEvaluator,
    run: AnalysisRun,
    include_history: bool,
    risks: tuple[Risk, ...] = ALL_RISKS,
) -> list[RiskFinding]:
    """Run every risk against one snapshot. Persist per-risk rows + upsert summaries."""
    logger.info(
        "analyse_snapshot: login=%s window=%s..%s risks=%d",
        snapshot.mt5_login,
        snapshot.start_time.isoformat(),
        snapshot.end_time.isoformat(),
        len(risks),
    )
    decisions = await prescreen_snapshot(
        snapshot, risks=risks, use_history=include_history
    )

    findings: list[RiskFinding] = []
    for risk in risks:
        if not decisions.get(risk.key, True):
            finding = _build_skipped_finding(risk=risk, snapshot=snapshot)
            ai_summary = None
        else:
            finding, ai_summary = await _evaluate_one(
                risk=risk,
                snapshot=snapshot,
                evaluator=evaluator,
                include_history=include_history,
            )
            logger.info(
                "risk evaluated login=%s risk=%s score=%d level=%s",
                snapshot.mt5_login,
                risk.key,
                finding.risk_score,
                finding.risk_level,
            )
        findings.append(finding)

        async with in_transaction():
            await RiskEvaluation.create(
                run=run,
                mt5_login=snapshot.mt5_login,
                risk_key=risk.key,
                risk_score=finding.risk_score,
                risk_level=finding.risk_level,
                trigger_type=snapshot.trigger_type,
                evidence=finding.evidence,
                suggested_action=finding.suggested_action,
                analysis=finding.analysis,
                behavior_summary=ai_summary,
                window_start=snapshot.start_time,
                window_end=snapshot.end_time,
            )
            if include_history and ai_summary is not None:
                await _upsert_summary(
                    mt5_login=snapshot.mt5_login,
                    risk_key=risk.key,
                    payload=ai_summary,
                    score=finding.risk_score,
                    level=finding.risk_level,
                )

    return findings


async def analyse_snapshots(
    *,
    snapshots: list[AccountSnapshot],
    evaluator: LLMEvaluator,
    include_history: bool,
    trigger_type: str = "manual_run",
) -> tuple[AnalysisRun, list[RiskFinding]]:
    """Top-level entry point used by the route."""
    run = await AnalysisRun.create(
        trigger_type=trigger_type,
        snapshot_count=len(snapshots),
    )
    logger.info(
        "analysis run started id=%s trigger=%s snapshots=%d include_history=%s",
        run.id,
        trigger_type,
        len(snapshots),
        include_history,
    )

    all_findings: list[RiskFinding] = []
    for snapshot in snapshots:
        findings = await analyse_snapshot(
            snapshot=snapshot,
            evaluator=evaluator,
            run=run,
            include_history=include_history,
        )
        all_findings.extend(findings)
    return run, all_findings
