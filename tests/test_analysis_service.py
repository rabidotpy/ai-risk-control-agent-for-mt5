"""Service-layer tests — the core history-aggregation contract."""

from __future__ import annotations

import json

import pytest

from app.models import AnalysisRun, RiskEvaluation, RiskHistorySummary
from app.risks import ALL_RISKS, LATENCY_ARBITRAGE
from app.schemas import AccountSnapshot
from app.services import analyse_snapshots

from .conftest import canned_response, make_short_trades, make_snapshot_payload


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
async def test_score_computed_from_python_rule_engine(db, evaluator):
    """Score now comes from the Python rule engine, not the LLM's
    canned `evaluations`. Build a snapshot that trips exactly 2/4
    latency-arbitrage rules (R1 trade_count + R2 median_hold), but
    leaves R3 (one-sided) and R4 (low win rate) failing → score 50.
    """
    _seed_responses(evaluator)
    trades = make_short_trades(n=30, side="buy", profit=-1.0)  # one-sided + losing
    snap = AccountSnapshot.model_validate(
        make_snapshot_payload(trades=trades)
    )
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


@pytest.mark.asyncio
async def test_llm_narration_skipped_below_threshold(db, evaluator, monkeypatch):
    """Low-score risks must not invoke the LLM. The deterministic score
    still lands in the finding; the narrative is a templated fallback.
    """
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_narrate_min_score", 60)
    _seed_responses(evaluator)  # canned responses exist but should not be used

    # Empty snapshot → every risk scores 0 (well below 60).
    snap = AccountSnapshot.model_validate(make_snapshot_payload())
    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    # All four risks return findings, all with scores < threshold.
    assert len(findings) == len(ALL_RISKS)
    assert all(f.risk_score < 60 for f in findings)
    # LLM was never invoked.
    assert evaluator.calls == []
    # The fallback narrative is a non-empty templated string (no LLM text).
    for f in findings:
        assert isinstance(f.analysis, str) and f.analysis
        # No LLM-derived behavior_summary was produced.
        assert f.behavior_summary is None


@pytest.mark.asyncio
async def test_evidence_description_list_comes_from_llm(db, evaluator):
    """When the LLM is called, its evidence_description_list is what we
    surface, verbatim. The Python service does not synthesise it."""
    from .conftest import canned_response, make_short_trades

    custom_lines = [
        "[WHAT] custom test what line",
        "[WHY] custom test why line",
        "[HOW] custom test how line",
        "[WHEN] custom test when line",
    ]
    # Seed only latency_arb with our custom list; the others use defaults.
    for risk in ALL_RISKS:
        if risk.key == LATENCY_ARBITRAGE.key:
            evaluator.responses[risk.key] = canned_response(
                sub_rules=risk.sub_rules,
                true_rules=risk.sub_rules,
                evidence_description_list=custom_lines,
            )
        else:
            evaluator.responses[risk.key] = canned_response(sub_rules=risk.sub_rules)

    # Trip all 4 latency rules so the LLM is actually invoked.
    trades = make_short_trades(n=30, side="buy", profit=1.0)
    for i in range(0, 30, 2):
        trades[i]["side"] = "sell"
    snap = AccountSnapshot.model_validate(make_snapshot_payload(trades=trades))

    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )
    la = next(f for f in findings if f.risk_type == LATENCY_ARBITRAGE.key)
    assert la.evidence_description_list == custom_lines


@pytest.mark.asyncio
async def test_evidence_description_list_empty_when_llm_skipped(
    db, evaluator, monkeypatch
):
    """Below the LLM threshold, no narration runs and the list stays []."""
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_narrate_min_score", 60)
    _seed_responses(evaluator)

    # Empty snapshot → all risks score 0, well below threshold.
    snap = AccountSnapshot.model_validate(make_snapshot_payload())
    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )
    assert all(f.evidence_description_list == [] for f in findings)


@pytest.mark.asyncio
async def test_evidence_description_list_filters_malformed_items(db):
    """If the LLM returns a list with non-strings or empty strings, those
    are silently dropped; surviving strings are kept."""
    from app.services import analyse_snapshot
    from .conftest import make_short_trades

    class CannedEvaluator:
        async def evaluate(self, risk, payload_json):
            return {
                "summary": "test",
                "behavior_summary": {"x": 1},
                "evidence_description_list": [
                    "[WHAT] kept item one",
                    "",                          # empty string, dropped
                    "   ",                       # whitespace only, dropped
                    None,                        # not a string, dropped
                    42,                          # not a string, dropped
                    "[WHEN] kept item two   ",   # stripped + kept
                ],
            }

    trades = make_short_trades(n=30, side="buy", profit=1.0)
    for i in range(0, 30, 2):
        trades[i]["side"] = "sell"
    snap = AccountSnapshot.model_validate(make_snapshot_payload(trades=trades))
    run = await AnalysisRun.create(trigger_type="manual_run", snapshot_count=1)

    findings = await analyse_snapshot(
        snapshot=snap, evaluator=CannedEvaluator(), run=run,
        include_history=False, risks=(LATENCY_ARBITRAGE,),
    )
    la = findings[0]
    assert la.evidence_description_list == [
        "[WHAT] kept item one",
        "[WHEN] kept item two",
    ]


@pytest.mark.asyncio
async def test_evidence_description_list_empty_when_llm_raises(db):
    """LLM exception: score is still computed, list stays []."""
    from app.services import analyse_snapshot
    from .conftest import make_short_trades

    class BoomEvaluator:
        async def evaluate(self, risk, payload_json):
            raise RuntimeError("boom: anthropic 500")

    trades = make_short_trades(n=30, side="buy", profit=1.0)
    for i in range(0, 30, 2):
        trades[i]["side"] = "sell"
    snap = AccountSnapshot.model_validate(make_snapshot_payload(trades=trades))
    run = await AnalysisRun.create(trigger_type="manual_run", snapshot_count=1)

    findings = await analyse_snapshot(
        snapshot=snap, evaluator=BoomEvaluator(), run=run,
        include_history=False, risks=(LATENCY_ARBITRAGE,),
    )
    la = findings[0]
    assert la.risk_score == 100  # rule engine still produced the verdict
    assert la.risk_level == "critical"
    assert la.evidence_description_list == []  # no list because LLM exploded
    assert "LLM narration unavailable" in la.analysis  # operator-visible


@pytest.mark.asyncio
async def test_evidence_description_list_empty_when_prescreen_skipped(
    db, evaluator, monkeypatch
):
    """Prescreen-skipped risks return an empty list (no LLM ran)."""
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "prescreen_enabled", True)
    _seed_responses(evaluator)

    snap = AccountSnapshot.model_validate(make_snapshot_payload())
    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=False
    )
    skipped = [f for f in findings if "prescreen" in f.evidence]
    assert skipped, "expected at least one prescreen-skipped risk on empty snapshot"
    for f in skipped:
        assert f.evidence_description_list == []


@pytest.mark.asyncio
async def test_llm_narration_runs_at_or_above_threshold(db, evaluator, monkeypatch):
    """At the threshold or above, the LLM is called and its narrative wins
    over the templated fallback.
    """
    from app.config import settings as app_settings
    from .conftest import make_short_trades
    monkeypatch.setattr(app_settings, "llm_narrate_min_score", 60)
    _seed_responses(
        evaluator,
        behavior={LATENCY_ARBITRAGE.key: {"run_count": 1, "marker": "from-llm"}},
    )

    # 30 short bidirectional all-winning scattered trades → latency arb = 4/4 = 100.
    trades = make_short_trades(n=30, side="buy", profit=1.0)
    for i in range(0, 30, 2):
        trades[i]["side"] = "sell"
    snap = AccountSnapshot.model_validate(make_snapshot_payload(trades=trades))

    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=True
    )

    la = next(f for f in findings if f.risk_type == LATENCY_ARBITRAGE.key)
    assert la.risk_score == 100
    # LLM was called for latency arb (it crossed threshold). At least one
    # call with that risk_key.
    assert any(rk == LATENCY_ARBITRAGE.key for rk, _ in evaluator.calls)
    # The behavior_summary came from the canned LLM response.
    assert la.behavior_summary == {"run_count": 1, "marker": "from-llm"}
