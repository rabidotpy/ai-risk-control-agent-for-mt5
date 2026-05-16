"""Shared types for the deterministic rule engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleOutcome:
    """One rule's verdict for one snapshot.

    `rule` is the exact rule text from the risk's SUB_RULES tuple.
    `observed_value` is the numeric value computed from the data (or None when
    the rule could not be evaluated). `true` is the deterministic verdict; if
    the rule could not be evaluated (insufficient data), `true` is False and
    `reason` starts with "insufficient_data:".
    """

    rule: str
    observed_value: Any
    true: bool
    reason: str


def insufficient(rule: str, reason: str) -> RuleOutcome:
    """Convenience constructor for the insufficient-data branch."""
    return RuleOutcome(
        rule=rule,
        observed_value=None,
        true=False,
        reason=f"insufficient_data: {reason}",
    )
