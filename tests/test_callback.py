"""Callback delivery — settings-driven, never raises."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.config import settings
from app.services import deliver


@pytest.mark.asyncio
async def test_skipped_when_no_url(monkeypatch):
    monkeypatch.setattr(settings, "callback_url", "")
    out = await deliver([{"x": 1}])
    assert out["status"] == "skipped"


@pytest.mark.asyncio
async def test_records_error_on_network_failure(monkeypatch):
    monkeypatch.setattr(settings, "callback_url", "http://does-not-resolve.invalid/cb")
    with patch.object(
        httpx.AsyncClient, "post", side_effect=httpx.ConnectError("boom")
    ):
        out = await deliver([{"x": 1}])
    assert out["status"] == "error"
    assert "boom" in out["reason"]


@pytest.mark.asyncio
async def test_marks_delivered_on_2xx(monkeypatch):
    monkeypatch.setattr(settings, "callback_url", "http://callback.test/cb")

    async def fake_post(self, url, *, json):
        return httpx.Response(200, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        out = await deliver([{"x": 1}])
    assert out["status"] == "delivered"
    assert out["http_status"] == 200
