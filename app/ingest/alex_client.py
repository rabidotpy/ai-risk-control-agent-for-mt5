"""Alex broker data feed — Phase B.

Two implementations behind one Protocol:

    StubAlexClient  — loads fixture JSON from disk. Default in dev / tests
                      so we can wire scheduler + aggregator end-to-end before
                      the broker endpoint exists.
    HttpAlexClient  — real GET against ALEX_BASE_URL with bearer-style auth.

Both return a parsed `AlexResponse`. Network / parse failures raise
`AlexFetchError` so the scan job can record + skip cleanly without taking
down the scheduler.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol

import requests

from .. import config
from ..schemas import AlexResponse


logger = logging.getLogger(__name__)


class AlexFetchError(RuntimeError):
    """Wraps any failure to obtain a usable AlexResponse."""


class AlexClient(Protocol):
    """Pluggable broker-data fetcher."""

    def fetch_window(self, *, start_time: datetime, end_time: datetime) -> AlexResponse:
        ...


# ---------------------------------------------------------------------------
# Stub client — loads from disk so dev and tests can run end-to-end without
# hitting the broker.
# ---------------------------------------------------------------------------


class StubAlexClient:
    """Reads `alex_window.json` (or a per-window file) from a fixtures dir.

    File-resolution order:
      1. <dir>/alex_<startISO>_<endISO>.json   (per-window override)
      2. <dir>/alex_window.json                (single canned response)

    The file's `start_time` / `end_time` are overridden with the requested
    window so the bucketing window-filter behaves identically to a real pull.
    """

    def __init__(self, fixtures_dir: str | Path | None = None):
        self._dir = Path(fixtures_dir or config.ALEX_STUB_FIXTURES_DIR)

    def fetch_window(self, *, start_time: datetime, end_time: datetime) -> AlexResponse:
        candidates = [
            self._dir / f"alex_{start_time.isoformat()}_{end_time.isoformat()}.json",
            self._dir / "alex_window.json",
        ]
        for path in candidates:
            if path.exists():
                try:
                    payload = json.loads(path.read_text())
                except json.JSONDecodeError as e:
                    raise AlexFetchError(f"stub fixture {path} is not valid JSON: {e}") from e
                # Override the window so downstream window-filtering matches
                # the requested slice regardless of what the fixture wrote.
                payload["start_time"] = start_time.isoformat()
                payload["end_time"] = end_time.isoformat()
                payload.setdefault("status", True)
                payload.setdefault("data", {})
                try:
                    return AlexResponse.model_validate(payload)
                except Exception as e:  # noqa: BLE001 — surface as AlexFetchError
                    raise AlexFetchError(
                        f"stub fixture {path} failed schema validation: {e}"
                    ) from e

        # No fixture present — return an empty but well-formed envelope so the
        # scheduler can run end-to-end in a fresh checkout.
        return AlexResponse.model_validate(
            {
                "status": True,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "data": {},
            }
        )


# ---------------------------------------------------------------------------
# HTTP client — real production fetch.
# ---------------------------------------------------------------------------


class HttpAlexClient:
    """GET ALEX_BASE_URL?start_time=<iso>&end_time=<iso> with bearer auth.

    The exact URL shape and auth header are kept simple here on purpose; when
    the broker endpoint lands we adjust this one method without touching the
    rest of the pipeline.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ):
        self._base_url = (base_url or config.ALEX_BASE_URL).rstrip("/")
        self._api_key = api_key or config.ALEX_API_KEY
        self._timeout = timeout if timeout is not None else config.ALEX_TIMEOUT_SECONDS
        if not self._base_url:
            raise AlexFetchError("ALEX_BASE_URL is not configured")

    def fetch_window(self, *, start_time: datetime, end_time: datetime) -> AlexResponse:
        params = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            resp = requests.get(
                self._base_url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise AlexFetchError(f"alex request failed: {type(e).__name__}: {e}") from e

        if not resp.ok:
            raise AlexFetchError(
                f"alex returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise AlexFetchError(f"alex response was not JSON: {e}") from e

        try:
            return AlexResponse.model_validate(payload)
        except Exception as e:  # noqa: BLE001
            raise AlexFetchError(f"alex response failed schema validation: {e}") from e


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_default_client() -> AlexClient:
    """Pick the client implementation based on ALEX_MODE config."""
    mode = config.ALEX_MODE
    if mode == "http":
        return HttpAlexClient()
    if mode == "stub":
        return StubAlexClient()
    raise ValueError(f"unknown ALEX_MODE: {mode!r} (expected 'stub' or 'http')")
