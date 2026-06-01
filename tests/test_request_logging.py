"""Tests for the request/response logging middleware."""

from __future__ import annotations

import json

import pytest

from app.config import settings
from app.models import RequestLog
from app.risks import ALL_RISKS

from .conftest import canned_response, make_snapshot_payload


def _seed(evaluator):
    for risk in ALL_RISKS:
        evaluator.responses[risk.key] = canned_response(sub_rules=risk.sub_rules)


@pytest.mark.asyncio
async def test_logs_analyse_risk_request_and_response(client, evaluator):
    _seed(evaluator)
    snap = make_snapshot_payload(mt5_login=70001)
    body = {"snapshots": [snap]}

    resp = await client.post("/analyse_risk", json=body)
    assert resp.status_code == 200

    rows = await RequestLog.all()
    assert len(rows) == 1
    row = rows[0]

    assert row.method == "POST"
    assert row.path == "/analyse_risk"
    assert row.status_code == 200
    assert row.duration_ms is not None and row.duration_ms >= 0
    assert row.error is None

    # Request body is stored as parsed JSON
    assert row.request_body == body
    # Response body is the findings list returned by the route
    assert isinstance(row.response_body, list)
    assert len(row.response_body) == len(ALL_RISKS)


@pytest.mark.asyncio
async def test_healthz_is_not_logged(client, db):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    # The middleware deliberately skips /healthz to avoid log spam from
    # liveness probes.
    assert await RequestLog.all().count() == 0


@pytest.mark.asyncio
async def test_analyses_get_is_not_logged_today(client, db):
    """GETs against the audit endpoints are not logged in this iteration.
    If we extend the logged set later, this test will fail and prompt
    us to update it."""
    resp = await client.get(
        "/analyses",
        params={"mt5_login": 99999, "start_time": "2026-05-08T00:00:00Z"},
    )
    # 404 because no rows for that login; that is fine, we are testing
    # the logging behaviour, not the route.
    assert resp.status_code == 404
    assert await RequestLog.all().count() == 0


@pytest.mark.asyncio
async def test_oversized_body_is_truncated(client, evaluator, monkeypatch):
    """Bodies above the cap are stored as a truncation marker so DB
    growth from a misbehaving client is bounded."""
    monkeypatch.setattr(settings, "request_log_max_body_bytes", 100)
    _seed(evaluator)
    snap = make_snapshot_payload(mt5_login=70001)
    body = {"snapshots": [snap]}  # well above 100 bytes

    resp = await client.post("/analyse_risk", json=body)
    assert resp.status_code == 200

    row = (await RequestLog.all())[0]
    assert isinstance(row.request_body, dict)
    assert row.request_body.get("_truncated") is True
    assert row.request_body.get("size", 0) > 100


@pytest.mark.asyncio
async def test_logging_disabled_skips_everything(client, evaluator, monkeypatch):
    monkeypatch.setattr(settings, "request_logging_enabled", False)
    _seed(evaluator)
    body = {"snapshots": [make_snapshot_payload(mt5_login=70001)]}

    resp = await client.post("/analyse_risk", json=body)
    assert resp.status_code == 200
    assert await RequestLog.all().count() == 0


@pytest.mark.asyncio
async def test_request_logs_endpoint_returns_recent_captures(client, evaluator):
    _seed(evaluator)
    # Make two requests we should be able to read back
    await client.post("/analyse_risk", json={"snapshots": [make_snapshot_payload(mt5_login=70001)]})
    await client.post("/analyse_risk", json={"snapshots": [make_snapshot_payload(mt5_login=70002)]})

    resp = await client.get("/request-logs?limit=5")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    # Newest first
    assert rows[0]["request_body"]["snapshots"][0]["mt5_login"] == 70002
    assert rows[1]["request_body"]["snapshots"][0]["mt5_login"] == 70001
    # All the right metadata is present
    for r in rows:
        assert r["method"] == "POST"
        assert r["path"] == "/analyse_risk"
        assert r["status_code"] == 200
        assert r["duration_ms"] is not None
        assert isinstance(r["response_body"], list)


@pytest.mark.asyncio
async def test_request_logs_endpoint_filters_by_status(client, db):
    # Make one bad request that will 422
    await client.post("/analyse_risk", json={"snapshots": "bad"})

    resp = await client.get("/request-logs?status=422")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["status_code"] == 422


@pytest.mark.asyncio
async def test_validation_error_request_still_logged(client, db):
    """Even a malformed payload should land in the log so we can debug
    'Alex sent garbage at 2pm'."""
    resp = await client.post("/analyse_risk", json={"snapshots": "not a list"})
    # Envelope normaliser doesn't accept a string, so this 422s. But the
    # request and the 422 response should both be captured.
    assert resp.status_code == 422

    rows = await RequestLog.all()
    assert len(rows) == 1
    assert rows[0].status_code == 422
    assert rows[0].request_body == {"snapshots": "not a list"}
    # Validation error response is JSON, captured as a dict with a `detail` key.
    assert isinstance(rows[0].response_body, dict)
    assert "detail" in rows[0].response_body
