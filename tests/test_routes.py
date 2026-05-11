"""HTTP-level tests against the FastAPI app."""

from __future__ import annotations

import pytest

from app.risks import ALL_RISKS

from .conftest import canned_response, make_snapshot_payload


def _seed(evaluator, **kw):
    for risk in ALL_RISKS:
        evaluator.responses[risk.key] = canned_response(sub_rules=risk.sub_rules, **kw)


def _envelope(*snapshots, include_history=None):
    body = {"snapshots": list(snapshots)}
    if include_history is not None:
        body["include_history"] = include_history
    return body


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_analyse_risk_single_snapshot_returns_one_finding_per_risk(
    client, evaluator, callback_fn
):
    _seed(evaluator)
    resp = await client.post("/analyse_risk", json=_envelope(make_snapshot_payload()))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == len(ALL_RISKS)
    assert {row["mt5_login"] for row in body} == {70001}
    assert callback_fn.calls == [body]


@pytest.mark.asyncio
async def test_analyse_risk_accepts_multiple_snapshots(client, evaluator, callback_fn):
    _seed(evaluator)
    payload = _envelope(
        make_snapshot_payload(mt5_login=70001),
        make_snapshot_payload(mt5_login=70002),
    )
    resp = await client.post("/analyse_risk", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2 * len(ALL_RISKS)
    assert len(callback_fn.calls) == 1


@pytest.mark.asyncio
async def test_analyse_risk_envelope_with_include_history_false(client, evaluator):
    _seed(evaluator)
    resp = await client.post(
        "/analyse_risk",
        json=_envelope(make_snapshot_payload(), include_history=False),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == len(ALL_RISKS)


@pytest.mark.asyncio
async def test_analyse_risk_empty_snapshots_returns_empty_list(client, evaluator):
    resp = await client.post("/analyse_risk", json=_envelope())
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_analyse_risk_validation_error_returns_422(client, evaluator):
    _seed(evaluator)
    bad = make_snapshot_payload()
    del bad["mt5_login"]
    resp = await client.post(
        "/analyse_risk",
        json=_envelope(make_snapshot_payload(), bad),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    # FastAPI's standard error shape — locates the offending snapshot at index 1.
    assert any(
        "snapshots" in err["loc"] and 1 in err["loc"] and "mt5_login" in err["loc"]
        for err in detail
    )


@pytest.mark.asyncio
async def test_get_history_returns_summary_after_first_run(client, evaluator):
    _seed(evaluator)
    await client.post(
        "/analyse_risk",
        json=_envelope(make_snapshot_payload(mt5_login=70001)),
    )

    resp = await client.get("/history", params={"mt5_login": 70001})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == len(ALL_RISKS)
    assert all(r["run_count"] == 1 for r in rows)


@pytest.mark.asyncio
async def test_get_analyses_returns_persisted_evaluations(client, evaluator):
    _seed(evaluator)
    snap = make_snapshot_payload(mt5_login=70001)
    await client.post("/analyse_risk", json=_envelope(snap))

    resp = await client.get(
        "/analyses",
        params={"mt5_login": 70001, "start_time": snap["start_time"]},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == len(ALL_RISKS)
    assert {r["risk_type"] for r in rows} == {r.key for r in ALL_RISKS}


@pytest.mark.asyncio
async def test_get_analyses_404_when_no_rows(client, db):
    resp = await client.get(
        "/analyses",
        params={"mt5_login": 99999, "start_time": "2026-05-08T00:00:00Z"},
    )
    assert resp.status_code == 404
