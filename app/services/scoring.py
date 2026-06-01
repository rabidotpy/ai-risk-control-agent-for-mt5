"""Score → level → suggested-action mapping.

Score formula: round(100 / N * count_true) where N is the number of
sub-rules. The level bands and suggested actions are stable contracts —
callers depend on the exact strings.
"""

from __future__ import annotations

from ..schemas import RiskLevel


def compute_score(num_sub_rules: int, num_true: int) -> int:
    if num_sub_rules <= 0:
        return 0
    return round(100 / num_sub_rules * num_true)


def score_to_level(score: int) -> RiskLevel:
    if score >= 90:
        return "critical"
    if score >= 75:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "watch"
    return "low"


_SUGGESTED_ACTION = {
    "low": "log_only",
    "watch": "add_to_watchlist",
    "medium": "manual_review",
    "high": "restrict_opening_pause_withdrawal",
    "critical": "restrict_opening_pause_withdrawal_high_priority",
}


def level_to_action(level: RiskLevel) -> str:
    return _SUGGESTED_ACTION[level]


# Per-risk dealing-desk actions. Compliance strings (above) are wrong for
# risks that flag profitable behaviour rather than abuse — locking down a
# profitable client is the opposite of what the broker wants. For those
# risks, this mapping carries the right operational guidance.
#
# Existing compliance-style risks are NOT in this map; they return None
# from `dealing_desk_action()` and the existing `suggested_action` field
# already gives the correct guidance.
_DEALING_DESK_ACTIONS: dict[str, dict[str, str | None]] = {
    "profitable_client_pattern": {
        "low": None,
        "watch": "monitor_in_dealing_desk",
        "medium": "flag_for_a_book_review",
        "high": "route_to_a_book",
        "critical": "route_to_a_book_urgent",
    },
}


def dealing_desk_action(risk_key: str, level: RiskLevel) -> str | None:
    """Operational action for risks where the compliance `suggested_action`
    is not the right framing.

    Returns None for risks that are pure compliance signals — in that
    case, `suggested_action` already gives the right answer.
    """
    mapping = _DEALING_DESK_ACTIONS.get(risk_key)
    if mapping is None:
        return None
    return mapping.get(level)
