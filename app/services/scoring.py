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
