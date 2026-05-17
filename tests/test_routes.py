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
    # Every persisted row carries the per-rule description list (list-typed,
    # even if empty for some skipped-prescreen cases).
    for r in rows:
        assert "evidence_description_list" in r
        assert isinstance(r["evidence_description_list"], list)


@pytest.mark.asyncio
async def test_get_analyses_404_when_no_rows(client, db):
    resp = await client.get(
        "/analyses",
        params={"mt5_login": 99999, "start_time": "2026-05-08T00:00:00Z"},
    )
    assert resp.status_code == 404


# -- Async / enqueue path -----------------------------------------------------


async def _wait_for_run_status(client, run_id, target, *, timeout=2.0):
    """Poll GET /runs/{id} until status reaches `target` or timeout."""
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    last = None
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/runs/{run_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last["status"] == target:
            return last
        await asyncio.sleep(0.02)
    raise AssertionError(
        f"run {run_id} never reached status={target}; last={last}"
    )


@pytest.mark.asyncio
async def test_analyse_risk_enqueue_returns_202_and_callback_fires(
    client, evaluator, callback_fn
):
    _seed(evaluator)
    payload = _envelope(make_snapshot_payload(mt5_login=70010))
    payload["enqueue_and_callback"] = True

    resp = await client.post("/analyse_risk", json=payload)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["snapshot_count"] == 1
    run_id = body["run_id"]
    assert body["poll_url"] == f"/runs/{run_id}"

    final = await _wait_for_run_status(client, run_id, "completed")
    assert final["callback_status"]["status"] == "delivered"
    assert final["error"] is None

    # Callback received exactly the same finding shape as the sync path.
    assert len(callback_fn.calls) == 1
    delivered = callback_fn.calls[0]
    assert len(delivered) == len(ALL_RISKS)
    assert {row["mt5_login"] for row in delivered} == {70010}


@pytest.mark.asyncio
async def test_get_run_404_for_unknown_id(client, db):
    resp = await client.get("/runs/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyse_risk_enqueue_503_when_worker_disabled(
    db, evaluator, callback_fn
):
    """If the queue exists but is disabled (concurrency=0) the enqueue
    path returns 503; the sync path still works."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app
    from app.services import JobQueue

    disabled_queue = JobQueue(
        evaluator_provider=lambda: evaluator,
        callback_fn=callback_fn,
        concurrency=0,
    )
    app = create_app(
        evaluator=evaluator,
        callback_fn=callback_fn,
        init_database=False,
        job_queue=disabled_queue,
    )
    _seed(evaluator)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = _envelope(make_snapshot_payload(mt5_login=70011))
        payload["enqueue_and_callback"] = True
        resp = await ac.post("/analyse_risk", json=payload)
        assert resp.status_code == 503
        assert resp.json()["detail"]["error"] == "job_worker_disabled"

        # Sync path on the same app still works.
        sync_resp = await ac.post(
            "/analyse_risk",
            json=_envelope(make_snapshot_payload(mt5_login=70011)),
        )
        assert sync_resp.status_code == 200
        assert len(sync_resp.json()) == len(ALL_RISKS)
