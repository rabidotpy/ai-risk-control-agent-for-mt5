"""Service-layer tests — the core history-aggregation contract."""

from __future__ import annotations

import json

import pytest

from app.models import AnalysisRun, RiskEvaluation, RiskHistorySummary
from app.risks import ALL_RISKS, LATENCY_ARBITRAGE
from app.schemas import AccountSnapshot
from app.services import analyse_snapshots

from .conftest import canned_response, make_snapshot_payload


def _seed_responses(evaluator, *, true_rules: dict[str, tuple[str, ...]] | None = None,
                    behavior: dict[str, dict] | None = None):
    """Seed canned responses for every risk in ALL_RISKS."""
    true_rules = true_rules or {}
    behavior = behavior or {}
    for risk in ALL_RISKS:
        evaluator.responses[risk.key] = canned_response(
            sub_rules=risk.sub_rules,
            true_rules=true_rules.get(risk.key, ()),
            behavior_summary=behavior.get(risk.key) or {"run_count": 1, "notes": "first"},
        )


@pytest.mark.asyncio
async def test_first_run_persists_one_evaluation_per_risk(db, evaluator):
    _seed_responses(evaluator)
    snap = AccountSnapshot.model_validate(make_snapshot_payload())

    run, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    assert len(findings) == len(ALL_RISKS)
    assert {f.risk_type for f in findings} == {r.key for r in ALL_RISKS}

    rows = await RiskEvaluation.filter(run_id=run.id).all()
    assert len(rows) == len(ALL_RISKS)


@pytest.mark.asyncio
async def test_first_run_creates_one_history_summary_per_risk(db, evaluator):
    _seed_responses(evaluator)
    snap = AccountSnapshot.model_validate(make_snapshot_payload(mt5_login=70001))

    await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    rows = await RiskHistorySummary.filter(mt5_login=70001).all()
    assert len(rows) == len(ALL_RISKS)
    for r in rows:
        assert r.run_count == 1


@pytest.mark.asyncio
async def test_second_run_feeds_prior_summary_into_prompt(db, evaluator):
    """The orchestrator MUST pass the previous run's behavior_summary as
    `prior_behavior_summary` on the second call."""
    _seed_responses(
        evaluator,
        behavior={LATENCY_ARBITRAGE.key: {"run_count": 1, "marker": "FIRST"}},
    )
    snap = AccountSnapshot.model_validate(make_snapshot_payload(mt5_login=70001))
    await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    # Reset call log; reseed the second response.
    evaluator.calls.clear()
    _seed_responses(
        evaluator,
        behavior={LATENCY_ARBITRAGE.key: {"run_count": 2, "marker": "SECOND"}},
    )
    await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    # Find the latency_arbitrage call from the second run.
    second_call = next(
        (payload for risk_key, payload in evaluator.calls if risk_key == LATENCY_ARBITRAGE.key),
        None,
    )
    assert second_call is not None
    body = json.loads(second_call)
    assert body["prior_behavior_summary"] == {"run_count": 1, "marker": "FIRST"}


@pytest.mark.asyncio
async def test_second_run_upserts_history_summary(db, evaluator):
    _seed_responses(
        evaluator,
        behavior={LATENCY_ARBITRAGE.key: {"run_count": 1, "marker": "FIRST"}},
    )
    snap = AccountSnapshot.model_validate(make_snapshot_payload(mt5_login=70001))
    await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    _seed_responses(
        evaluator,
        behavior={LATENCY_ARBITRAGE.key: {"run_count": 2, "marker": "SECOND"}},
    )
    await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    summary = await RiskHistorySummary.get(
        mt5_login=70001, risk_key=LATENCY_ARBITRAGE.key
    )
    assert summary.run_count == 2
    assert summary.payload == {"run_count": 2, "marker": "SECOND"}


@pytest.mark.asyncio
async def test_include_history_false_skips_prior_load_and_upsert(db, evaluator):
    _seed_responses(evaluator)
    snap = AccountSnapshot.model_validate(make_snapshot_payload(mt5_login=70002))

    await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=False
    )

    # No history rows when the switch is off.
    rows = await RiskHistorySummary.filter(mt5_login=70002).all()
    assert rows == []

    # Prompt did not carry a prior summary either.
    for _, payload in evaluator.calls:
        assert json.loads(payload)["prior_behavior_summary"] is None


@pytest.mark.asyncio
async def test_score_computed_from_true_rule_count(db, evaluator):
    # Force latency_arbitrage to fire 2/4 rules → 50.
    _seed_responses(
        evaluator,
        true_rules={
            LATENCY_ARBITRAGE.key: (
                "trade_count_6h >= 30",
                "median_holding_time_seconds <= 30",
            )
        },
    )
    snap = AccountSnapshot.model_validate(make_snapshot_payload())
    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )
    la = next(f for f in findings if f.risk_type == LATENCY_ARBITRAGE.key)
    assert la.risk_score == 50
    assert la.risk_level == "watch"


@pytest.mark.asyncio
async def test_run_record_is_created(db, evaluator):
    _seed_responses(evaluator)
    snap = AccountSnapshot.model_validate(make_snapshot_payload())
    await analyse_snapshots(
        snapshots=[snap, snap], evaluator=evaluator, include_history=True
    )
    runs = await AnalysisRun.all()
    assert len(runs) == 1
    assert runs[0].snapshot_count == 2
