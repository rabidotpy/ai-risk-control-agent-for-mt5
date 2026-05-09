"""Best-effort callback delivery.

POSTs the analysis result to CALLBACK_URL. Failures are recorded in the
returned dict but never raise — System B already gets the result in the
HTTP response body, so a callback failure should not fail the request.
"""

from __future__ import annotations

from typing import Any

import requests

from . import config


def deliver(result_body: dict[str, Any]) -> dict[str, Any]:
    """Returns a small status dict the caller embeds in the response for diagnostics."""

    url = config.CALLBACK_URL.strip()
    if not url:
        return {"url": None, "status": "skipped", "reason": "no CALLBACK_URL configured"}

    try:
        resp = requests.post(
            url,
            json=result_body,
            timeout=config.CALLBACK_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        return {"url": url, "status": "error", "reason": f"{type(e).__name__}: {e}"}

    return {
        "url": url,
        "status": "delivered" if resp.ok else "rejected",
        "http_status": resp.status_code,
    }
