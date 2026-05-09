"""Risk-analysis engine.

Takes an AccountSnapshot (one account's slice of the broker pull) and
produces four RiskResult rows by fanning out four parallel Claude calls.
Re-runs always re-evaluate; the persistence layer overwrites stored rows
on the (mt5_login, start_time, risk_type) key.

Score formula: round(100 / N * count_true) where N is the number of
sub-rules. Score → risk_level → suggested_action follows PRD §6.4.

Phase B: `historical_context` is an optional dict carrying long-window
counters (24h / 72h / 30d) and verdict trend. When present, the engine
serialises it alongside the current window so the LLM can evaluate
literal PRD-window rules (e.g. scalping `trade_count_24h >= 100`) and
the shared trend rule (`prior_high_or_critical_in_last_5_scans`). When
absent, those rules return insufficient_data and don't fire.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .llm import LLMEvaluator
from .risks import ALL_RISKS, Risk
from .schemas import AccountSnapshot, RiskLevel, RiskResult, TriggerType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score → level → suggested-action mapping (PRD §6.4)
# ---------------------------------------------------------------------------


def compute_score(num_sub_rules: int, num_true: int) -> int:
    if num_sub_rules <= 0:
        return 0
    return round(100 / num_sub_rules * num_true)


def score_to_level(score: int) -> RiskLevel:
    if score >= 90:
        return "critical"
    if score >= 75:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "watch"
    return "low"


_SUGGESTED_ACTION = {
    "low": "log_only",
    "watch": "add_to_watchlist",
    "medium": "manual_review",
    "high": "restrict_opening_pause_withdrawal",
    "critical": "restrict_opening_pause_withdrawal_high_priority",
}


def level_to_action(level: RiskLevel) -> str:
    return _SUGGESTED_ACTION[level]


# ---------------------------------------------------------------------------
# Helpers for parsing the LLM tool output
# ---------------------------------------------------------------------------


_COMPARISON_OPS = (" >= ", " <= ", " > ", " < ", " == ")


def _metric_name(rule: str) -> str:
    """Strip the comparison + threshold from a rule string.

    'trade_count_6h >= 30' → 'trade_count_6h'
    'repeated_lot_sl_tp_pattern_present' → 'repeated_lot_sl_tp_pattern_present'
    """
    for op in _COMPARISON_OPS:
        if op in rule:
            return rule.split(op, 1)[0]
    return rule


def _build_evidence(evaluations: list[Any], allowed_rules: tuple[str, ...]) -> dict[str, Any]:
    """Surface observed_value per rule, keyed by metric name."""
    out: dict[str, Any] = {}
    for ev in evaluations:
        if not isinstance(ev, dict):
            continue
        rule = ev.get("rule")
        if not isinstance(rule, str) or rule not in allowed_rules:
            continue
        value = ev.get("observed_value")
        if value is None:
            continue
        out[_metric_name(rule)] = value
    return out


def _count_true_sub_rules(
    evaluations: list[Any], allowed_rules: tuple[str, ...]
) -> int:
    """Count sub-rules the model marked true, deduped by exact rule text."""
    seen: set[str] = set()
    for ev in evaluations:
        if not isinstance(ev, dict):
            continue
        rule = ev.get("rule")
        if (
            isinstance(rule, str)
            and rule in allowed_rules
            and ev.get("true")
            and rule not in seen
        ):
            seen.add(rule)
    return len(seen)


def _build_result(
    *,
    risk: Risk,
    tool_input: dict[str, Any],
    mt5_login: int,
    trigger_type: TriggerType,
) -> RiskResult:
    evaluations = tool_input.get("evaluations") or []
    summary = tool_input.get("summary") or ""

    num_true = _count_true_sub_rules(evaluations, risk.sub_rules)
    score = compute_score(risk.num_sub_rules, num_true)
    level = score_to_level(score)
    action = level_to_action(level)
    evidence = _build_evidence(evaluations, risk.sub_rules)

    return RiskResult(
        mt5_login=mt5_login,
        risk_type=risk.key,
        risk_score=score,
        risk_level=level,
        trigger_type=trigger_type,
        evidence=evidence,
        suggested_action=action,
        analysis=summary,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def analyse(
    snapshot: AccountSnapshot,
    evaluator: LLMEvaluator,
    risks: tuple[Risk, ...] = ALL_RISKS,
    historical_context: dict[str, Any] | None = None,
) -> list[RiskResult]:
    """Evaluate every risk in `risks` against `snapshot` using `evaluator`.

    The user-message payload is the wrapped envelope:
        {
            "current_window": <AccountSnapshot as JSON>,
            "historical_context": <dict | null>
        }
    `historical_context` carries 24h / 72h / 30d aggregations and
    verdict-trend counts produced by `app.history.aggregator`.
    """

    payload_json = json.dumps(
        {
            "current_window": json.loads(snapshot.model_dump_json()),
            "historical_context": historical_context,
        },
        separators=(",", ":"),
    )

    def evaluate_one(risk: Risk) -> RiskResult:
        try:
            tool_input = evaluator.evaluate(risk, payload_json)
            return _build_result(
                risk=risk,
                tool_input=tool_input,
                mt5_login=snapshot.mt5_login,
                trigger_type=snapshot.trigger_type,
            )
        except Exception as exc:  # noqa: BLE001 — contain per-risk failure
            # A single risk failing (network blip, rate limit, malformed tool
            # response) must NOT lose the other three analyses for this
            # account. Return a zero-score row tagged as errored so the
            # caller and the persistence layer still get a complete set.
            logger.exception(
                "risk evaluation failed for login=%s risk=%s",
                snapshot.mt5_login,
                risk.key,
            )
            return RiskResult(
                mt5_login=snapshot.mt5_login,
                risk_type=risk.key,
                risk_score=0,
                risk_level="low",
                trigger_type=snapshot.trigger_type,
                evidence={"error": f"{type(exc).__name__}: {exc}"},
                suggested_action=level_to_action("low"),
                analysis=f"error: evaluation failed ({type(exc).__name__})",
            )

    # N risks → N threads. The work is I/O-bound (Claude HTTP calls).
    with ThreadPoolExecutor(max_workers=len(risks)) as pool:
        results = list(pool.map(evaluate_one, risks))

    return results
