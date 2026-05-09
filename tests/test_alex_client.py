"""Tests for app/ingest/alex_client.py."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.ingest.alex_client import (
    AlexFetchError,
    HttpAlexClient,
    StubAlexClient,
    get_default_client,
)


def test_stub_returns_empty_envelope_when_no_fixture(tmp_path):
    client = StubAlexClient(fixtures_dir=tmp_path)
    s = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)
    e = s + timedelta(hours=6)
    env = client.fetch_window(start_time=s, end_time=e)
    assert env.start_time == s
    assert env.end_time == e
    assert env.data.trades == []


def test_stub_loads_alex_window_json_and_overrides_times(tmp_path: Path):
    fixture = {
        "status": True,
        "start_time": "2000-01-01T00:00:00+00:00",
        "end_time": "2000-01-01T06:00:00+00:00",
        "data": {"deposits": [], "withdraws": [], "trades": [], "bonus": []},
    }
    (tmp_path / "alex_window.json").write_text(json.dumps(fixture))

    client = StubAlexClient(fixtures_dir=tmp_path)
    s = datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)
    e = s + timedelta(hours=6)
    env = client.fetch_window(start_time=s, end_time=e)
    assert env.start_time == s
    assert env.end_time == e


def test_stub_invalid_json_raises_alex_fetch_error(tmp_path: Path):
    (tmp_path / "alex_window.json").write_text("not json")
    client = StubAlexClient(fixtures_dir=tmp_path)
    with pytest.raises(AlexFetchError):
        client.fetch_window(
            start_time=datetime(2026, 5, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 9, 6, tzinfo=timezone.utc),
        )


def test_http_client_requires_base_url(monkeypatch):
    monkeypatch.setattr("app.ingest.alex_client.config.ALEX_BASE_URL", "")
    with pytest.raises(AlexFetchError):
        HttpAlexClient()


def test_get_default_client_respects_mode(monkeypatch):
    monkeypatch.setattr("app.ingest.alex_client.config.ALEX_MODE", "stub")
    assert isinstance(get_default_client(), StubAlexClient)
    monkeypatch.setattr("app.ingest.alex_client.config.ALEX_MODE", "bogus")
    with pytest.raises(ValueError):
        get_default_client()
