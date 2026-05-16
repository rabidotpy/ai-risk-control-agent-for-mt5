"""User-message payload builder.

The user message is one JSON object with three keys:
  current_window         — the AccountSnapshot, JSON-serialised.
  rule_outcomes          — list of {rule, observed_value, true, reason}
                           dicts produced by the deterministic rule
                           engine. Authoritative for the model.
  prior_behavior_summary — dict | None — the AI's last summary for this
                           (mt5_login, risk_key), or None if there isn't
                           one yet.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable

from ..schemas import AccountSnapshot


def build_user_payload(
    snapshot: AccountSnapshot,
    prior_behavior_summary: dict[str, Any] | None,
    rule_outcomes: Iterable[Any] = (),
) -> str:
    """Serialise the three-block envelope the model expects."""
    outcomes = [
        asdict(o) if hasattr(o, "__dataclass_fields__") else dict(o)
        for o in rule_outcomes
    ]
    return json.dumps(
        {
            "current_window": json.loads(snapshot.model_dump_json()),
            "rule_outcomes": outcomes,
            "prior_behavior_summary": prior_behavior_summary,
        },
        separators=(",", ":"),
    )
