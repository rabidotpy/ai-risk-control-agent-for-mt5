"""Best-effort callback delivery.

POSTs the analysis result to `settings.callback_url`. Failures are
recorded in the returned dict but never raise — the HTTP response
already carries the analysis body, so a callback failure must not fail
the request.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings


logger = logging.getLogger(__name__)


async def deliver(result_body: list[dict[str, Any]]) -> dict[str, Any]:
    """Returns a small status dict the caller embeds in the run record."""
    url = settings.callback_url.strip()
    if not url:
        return {"url": None, "status": "skipped", "reason": "no callback_url configured"}

    try:
        async with httpx.AsyncClient(timeout=settings.callback_timeout_seconds) as client:
            resp = await client.post(url, json=result_body)
    except httpx.HTTPError as e:
        logger.warning("callback delivery failed: %s", e)
        return {"url": url, "status": "error", "reason": f"{type(e).__name__}: {e}"}

    return {
        "url": url,
        "status": "delivered" if resp.is_success else "rejected",
        "http_status": resp.status_code,
    }
