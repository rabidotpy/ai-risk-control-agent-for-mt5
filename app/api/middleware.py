"""Request/response logging middleware.

Captures every HTTP call to the logged endpoint set, writes a row to the
`request_log` table, and emits a one-line summary to stdout. The route
handler is unchanged: the middleware intercepts request and response at
the ASGI layer.

Design choices:
  - Scope is limited to /analyse_risk for now. /healthz is too chatty to
    log; audit GETs (/analyses, /history, /runs/:id) can be added later
    if needed.
  - Bodies are stored as JSONB when parseable, or as `{"_raw": "..."}`
    when not. Bodies above `settings.request_log_max_body_bytes` are
    stored as `{"_truncated": true, "size": N}` to keep DB growth bounded.
  - DB writes are best-effort: if storage fails we still let the request
    succeed and log a warning. We never break the real flow over an
    audit-log failure.
  - The stdout summary is greppable: method, path, status, duration, plus
    a few keys parsed from the request envelope when present.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..config import settings


logger = logging.getLogger(__name__)


# Paths whose request + response we always log. /healthz is intentionally
# excluded — it would dominate the log with no signal.
_LOGGED_PATHS: frozenset[str] = frozenset({"/analyse_risk"})


def _parse_body(raw: bytes, max_bytes: int) -> Any:
    """Best-effort decode of a body bytes blob to a JSON-safe value."""
    size = len(raw)
    if size == 0:
        return None
    if size > max_bytes:
        return {"_truncated": True, "size": size}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Not JSON. Store the first 256 bytes as a debug aid.
        return {"_raw": raw[:256].decode("utf-8", errors="replace")}


def _summarise_request(body: Any) -> str:
    """One-line summary of an /analyse_risk request body for stdout."""
    if not isinstance(body, dict):
        return ""
    snapshots = body.get("snapshots")
    if isinstance(snapshots, dict):
        # User sent {"snapshots": {...}} — the envelope-normaliser will fix
        # this but the original shape is informative.
        snapshots = [snapshots]
    if isinstance(body.get("snapshot"), dict):
        snapshots = [body["snapshot"]]
    if not isinstance(snapshots, list):
        return ""
    logins = []
    total_trades = 0
    for s in snapshots:
        if not isinstance(s, dict):
            continue
        login = s.get("mt5_login")
        if login is not None:
            logins.append(str(login))
        trades = s.get("trades")
        if isinstance(trades, list):
            total_trades += len(trades)
    parts = [f"snapshots={len(snapshots)}"]
    if logins:
        parts.append(f"logins=[{','.join(logins[:5])}{'...' if len(logins) > 5 else ''}]")
    parts.append(f"trades={total_trades}")
    return " ".join(parts)


def _summarise_response(body: Any, status: int) -> str:
    """One-line summary of a response body."""
    if isinstance(body, list):
        return f"findings={len(body)}"
    if isinstance(body, dict):
        if "run_id" in body:
            return f"run_id={body['run_id']}"
        if "detail" in body:
            return f"detail=true"
    return ""


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Stores request + response for logged paths; emits stdout summaries."""

    async def dispatch(self, request: Request, call_next):
        # Fast path: skip unlogged routes entirely.
        if not settings.request_logging_enabled or request.url.path not in _LOGGED_PATHS:
            return await call_next(request)

        # Capture the request body. Starlette consumes the underlying
        # receive() once, so we have to re-inject a receive callable that
        # replays the bytes for the downstream handler.
        raw_request = await request.body()

        async def _replay() -> dict:
            return {"type": "http.request", "body": raw_request, "more_body": False}

        request._receive = _replay  # type: ignore[attr-defined]

        max_bytes = settings.request_log_max_body_bytes
        parsed_request = _parse_body(raw_request, max_bytes)

        start = time.perf_counter()
        status_code: int | None = None
        error_text: str | None = None
        raw_response = b""

        try:
            response = await call_next(request)
            status_code = response.status_code
            # Drain the response body so we can both log it AND return it.
            async for chunk in response.body_iterator:
                raw_response += chunk
            # Rebuild a Response from the drained bytes; the original
            # `response` is no longer usable once its iterator is consumed.
            response = Response(
                content=raw_response,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
            # Content-Length may have changed if Starlette set it from a
            # streaming body; ensure it matches the captured bytes.
            response.headers["content-length"] = str(len(raw_response))
        except Exception as exc:  # noqa: BLE001 — we re-raise after logging
            error_text = f"{type(exc).__name__}: {exc}"
            duration_ms = int((time.perf_counter() - start) * 1000)
            await self._persist(
                request=request,
                request_body=parsed_request,
                response_body=None,
                status_code=None,
                error_text=error_text,
                duration_ms=duration_ms,
            )
            logger.exception(
                "%s %s ERROR %dms %s",
                request.method, request.url.path, duration_ms, error_text,
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        parsed_response = _parse_body(raw_response, max_bytes)

        await self._persist(
            request=request,
            request_body=parsed_request,
            response_body=parsed_response,
            status_code=status_code,
            error_text=None,
            duration_ms=duration_ms,
        )

        req_summary = _summarise_request(parsed_request)
        resp_summary = _summarise_response(parsed_response, status_code or 0)
        logger.info(
            "%s %s %d %dms %s %s",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
            req_summary,
            resp_summary,
        )

        return response

    @staticmethod
    async def _persist(
        *,
        request: Request,
        request_body: Any,
        response_body: Any,
        status_code: int | None,
        error_text: str | None,
        duration_ms: int,
    ) -> None:
        """Insert a RequestLog row. Best-effort — never raises."""
        # Local import keeps the middleware module test-importable without
        # triggering Tortoise's app-not-ready guard.
        from ..models import RequestLog

        client_host = request.client.host if request.client else None
        try:
            await RequestLog.create(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                request_body=request_body,
                response_body=response_body,
                error=error_text,
                duration_ms=duration_ms,
                client_host=client_host,
            )
        except Exception as exc:  # noqa: BLE001 — never break the request
            logger.warning(
                "request_log persistence failed: %s: %s — request still served",
                type(exc).__name__, exc,
            )
