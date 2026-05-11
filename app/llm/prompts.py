"""User-message payload builder.

The user message is one JSON object with two keys:
  current_window         — the AccountSnapshot, JSON-serialised.
  prior_behavior_summary — dict | None — the AI's last summary for this
                           (mt5_login, risk_key), or None if there isn't
                           one yet.
"""

from __future__ import annotations

import json
from typing import Any

from ..schemas import AccountSnapshot


def build_user_payload(
    snapshot: AccountSnapshot,
    prior_behavior_summary: dict[str, Any] | None,
) -> str:
    """Serialise the two-block envelope the model expects."""
    return json.dumps(
        {
            "current_window": json.loads(snapshot.model_dump_json()),
            "prior_behavior_summary": prior_behavior_summary,
        },
        separators=(",", ":"),
    )
