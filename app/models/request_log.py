"""Per-request audit log.

One row per HTTP call to a logged endpoint (currently `/analyse_risk`).
Stores enough to answer "what did Alex send us at 13:42 and what did we
return?" without grovelling through tcpdump or production stdout.

Bodies are stored as JSONB when parseable, or as a `{"_raw": "..."}`
fallback when they are not. Bodies above `settings.request_log_max_body_bytes`
are stored as `{"_truncated": true, "size": N}` to keep DB growth bounded.
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class RequestLog(Model):
    """One HTTP request + its response."""

    id = fields.IntField(primary_key=True)
    timestamp = fields.DatetimeField(auto_now_add=True)
    method = fields.CharField(max_length=8)
    path = fields.CharField(max_length=256)
    status_code = fields.IntField(null=True)
    request_body = fields.JSONField(null=True)
    response_body = fields.JSONField(null=True)
    error = fields.TextField(null=True)
    duration_ms = fields.IntField(null=True)
    client_host = fields.CharField(max_length=64, null=True)

    class Meta:
        table = "request_log"
        indexes = (
            ("timestamp",),
            ("path", "timestamp"),
        )
