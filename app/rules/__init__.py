"""Deterministic rule engine.

Public surface:
  RuleOutcome     — one rule's verdict for one snapshot.
  insufficient    — convenience constructor for the insufficient-data branch.
  EVALUATORS      — risk_key -> evaluate(snapshot) -> list[RuleOutcome].

The per-risk SUB_RULES tuples live in each `app/rules/<risk>.py` module and
are re-exported by `app/risks/<risk>.py` so the rest of the codebase has a
single source of truth.
"""

from __future__ import annotations

from typing import Callable

from ..schemas import AccountSnapshot
from . import bonus_abuse, latency_arbitrage, scalping, swap_arbitrage
from .types import RuleOutcome, insufficient


EVALUATORS: dict[str, Callable[[AccountSnapshot], list[RuleOutcome]]] = {
    "latency_arbitrage": latency_arbitrage.evaluate,
    "scalping": scalping.evaluate,
    "swap_arbitrage": swap_arbitrage.evaluate,
    "bonus_abuse": bonus_abuse.evaluate,
}


__all__ = [
    "EVALUATORS",
    "RuleOutcome",
    "bonus_abuse",
    "insufficient",
    "latency_arbitrage",
    "scalping",
    "swap_arbitrage",
]
