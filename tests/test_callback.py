"""Callback delivery — failure modes and skip-when-unconfigured."""

from __future__ import annotations

from unittest.mock import patch

import requests

from app import callback


def test_skips_when_url_not_configured(monkeypatch):
    monkeypatch.setattr(callback.config, "CALLBACK_URL", "")
    status = callback.deliver({"hello": "world"})
    assert status["status"] == "skipped"
    assert status["url"] is None


def test_records_http_status_on_success(monkeypatch):
    monkeypatch.setattr(callback.config, "CALLBACK_URL", "https://example.test/cb")

    class FakeResponse:
        ok = True
        status_code = 200

    with patch.object(requests, "post", return_value=FakeResponse()) as mock_post:
        status = callback.deliver({"hello": "world"})

    assert status == {
        "url": "https://example.test/cb",
        "status": "delivered",
        "http_status": 200,
    }
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"hello": "world"}


def test_records_rejected_on_4xx(monkeypatch):
    monkeypatch.setattr(callback.config, "CALLBACK_URL", "https://example.test/cb")

    class FakeResponse:
        ok = False
        status_code = 422

    with patch.object(requests, "post", return_value=FakeResponse()):
        status = callback.deliver({})

    assert status["status"] == "rejected"
    assert status["http_status"] == 422


def test_records_error_on_network_failure(monkeypatch):
    monkeypatch.setattr(callback.config, "CALLBACK_URL", "https://example.test/cb")

    with patch.object(requests, "post", side_effect=requests.ConnectionError("boom")):
        status = callback.deliver({})

    assert status["status"] == "error"
    assert "ConnectionError" in status["reason"]
