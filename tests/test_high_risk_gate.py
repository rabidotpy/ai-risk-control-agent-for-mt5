"""Tests for the high-risk gating wired through the FastAPI route.

Verifies two things end-to-end:

1.  The post-LLM filter (`callback_min_score`) drops low-score accounts
    from BOTH the HTTP response and the callback payload, while
    keeping every row in the audit trail (`/analyses`).
2.  The pre-LLM gate (`prescreen_enabled`) skips the LLM entirely for
    risks that no rule can plausibly trip — but still persists a stub
    `RiskEvaluation` row so the audit trail stays complete.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.risks import ALL_RISKS

from .conftest import canned_response, make_snapshot_payload


def _seed_all_true(evaluator):
    """Every risk fires every sub-rule → max score per risk."""
    for risk in ALL_RISKS:
        evaluator.responses[risk.key] = canned_response(
            sub_rules=risk.sub_rules, true_rules=risk.sub_rules
        )


def _seed_no_rules(evaluator):
    for risk in ALL_RISKS:
        evaluator.responses[risk.key] = canned_response(sub_rules=risk.sub_rules)


def _envelope(*snapshots):
    return {"snapshots": list(snapshots)}


@pytest.mark.asyncio
async def test_low_risk_account_dropped_from_response_and_callback(
    client, evaluator, callback_fn, monkeypatch
):
    monkeypatch.setattr(settings, "callback_min_score", 60)

    _seed_all_true(evaluator)

    payload = _envelope(
        make_snapshot_payload(mt5_login=70001),  # max score → kept
        make_snapshot_payload(mt5_login=70002),  # max score → kept
    )
    resp = await client.post("/analyse_risk", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert {row["mt5_login"] for row in body} == {70001, 70002}
    assert callback_fn.calls == [body]

    # Now drop everything by raising the threshold.
    callback_fn.calls.clear()
    monkeypatch.setattr(settings, "callback_min_score", 999)
    resp = await client.post("/analyse_risk", json=payload)
    assert resp.status_code == 200
    assert resp.json() == []
    assert callback_fn.calls == [[]]


@pytest.mark.asyncio
async def test_audit_trail_keeps_dropped_accounts(client, evaluator, monkeypatch):
    monkeypatch.setattr(settings, "callback_min_score", 999)
    _seed_all_true(evaluator)

    snapshot = make_snapshot_payload(mt5_login=70001)
    resp = await client.post("/analyse_risk", json=_envelope(snapshot))
    assert resp.status_code == 200
    assert resp.json() == []

    # Persistence is unaffected by the outbound filter.
    audit = await client.get(
        "/analyses",
        params={"mt5_login": 70001, "start_time": snapshot["start_time"]},
    )
    assert audit.status_code == 200
    rows = audit.json()
    assert len(rows) == len(ALL_RISKS)
    assert all(r["risk_score"] > 0 for r in rows)


@pytest.mark.asyncio
async def test_prescreen_persists_stubs_and_skips_llm(
    client, evaluator, callback_fn, monkeypatch
):
    monkeypatch.setattr(settings, "prescreen_enabled", True)
    monkeypatch.setattr(settings, "callback_min_score", 0)

    _seed_no_rules(evaluator)
    snapshot = make_snapshot_payload(mt5_login=70010)  # empty trades → all skip
    resp = await client.post("/analyse_risk", json=_envelope(snapshot))
    assert resp.status_code == 200
    body = resp.json()

    # All four risks are returned as zero-score stubs (min_score=0 so
    # the outbound filter is a no-op here).
    assert len(body) == len(ALL_RISKS)
    assert {row["risk_score"] for row in body} == {0}
    assert {row["risk_level"] for row in body} == {"low"}
    assert all("prescreen" in row["evidence"] for row in body)

    # The LLM was never invoked because every risk was prescreened out.
    assert evaluator.calls == []

    # The audit trail also has the stubs.
    audit = await client.get(
        "/analyses",
        params={"mt5_login": 70010, "start_time": snapshot["start_time"]},
    )
    assert audit.status_code == 200
    assert len(audit.json()) == len(ALL_RISKS)
