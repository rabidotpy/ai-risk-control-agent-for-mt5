"""Cheap deterministic gate that runs before the LLM.

Purpose: minimise Anthropic token spend AND analyst attention. Risks
whose prescreen returns False on a snapshot are not sent to Claude — a
synthetic `risk_score=0` row is persisted instead so the audit trail
stays complete (see `analyse_snapshot`).

Bar is intentionally low: false positives only waste one LLM call,
false negatives let real risk escape. When in doubt, return True.

Override: if the prior `RiskHistorySummary.last_score` for an account is
already at or above `settings.callback_min_score`, prescreen returns
True regardless — repeat offenders are always re-evaluated.
"""

from __future__ import annotations

import logging
from typing import Callable

from ..config import settings
from ..models import RiskHistorySummary
from ..risks import ALL_RISKS, Risk
from ..schemas import AccountSnapshot


logger = logging.getLogger(__name__)


# Per-risk minimum trade count thresholds. Set well below the real
# rule thresholds in `app.risks.*` so we never reject a snapshot the
# LLM might still find interesting.
_LATENCY_MIN_TRADES = 20  # rule fires at 30
_SCALPING_MIN_TRADES = 15  # rule fires at 25


def _prescreen_latency_arbitrage(snapshot: AccountSnapshot) -> bool:
    return len(snapshot.trades) >= _LATENCY_MIN_TRADES


def _prescreen_scalping(snapshot: AccountSnapshot) -> bool:
    return len(snapshot.trades) >= _SCALPING_MIN_TRADES


def _prescreen_swap_arbitrage(snapshot: AccountSnapshot) -> bool:
    # Any non-zero swap means rollover exposure — let the LLM judge
    # whether it's dominant. Zero-swap snapshots are pure intraday and
    # cannot trip any of the four sub-rules.
    return any((t.swaps or 0) != 0 for t in snapshot.trades)


def _prescreen_bonus_abuse(snapshot: AccountSnapshot) -> bool:
    # Any one of: bonus event in window, multiple linked accounts, or
    # withdrawal activity. Without any of these, none of the five
    # sub-rules can fire.
    return (
        len(snapshot.bonus) > 0
        or len(snapshot.linked_accounts) >= 2
        or len(snapshot.withdraws) > 0
    )


# Map risk_key → callable. Adding a new risk = add a new entry here.
_PRESCREENS: dict[str, Callable[[AccountSnapshot], bool]] = {
    "latency_arbitrage": _prescreen_latency_arbitrage,
    "scalping": _prescreen_scalping,
    "swap_arbitrage": _prescreen_swap_arbitrage,
    "bonus_abuse": _prescreen_bonus_abuse,
}


async def _has_prior_high_risk(*, mt5_login: int, risk_key: str) -> bool:
    """True if the last stored score for this (login, risk) is already actionable."""
    prior = await RiskHistorySummary.get_or_none(
        mt5_login=mt5_login, risk_key=risk_key
    )
    if prior is None:
        return False
    return prior.last_score >= settings.callback_min_score


async def prescreen_snapshot(
    snapshot: AccountSnapshot,
    *,
    risks: tuple[Risk, ...] = ALL_RISKS,
    use_history: bool,
) -> dict[str, bool]:
    """Returns {risk_key: should_run_llm} for every risk.

    When `settings.prescreen_enabled` is False every risk maps to True
    (i.e. no gating — the LLM evaluates everything).
    """
    if not settings.prescreen_enabled:
        return {risk.key: True for risk in risks}

    decisions: dict[str, bool] = {}
    for risk in risks:
        check = _PRESCREENS.get(risk.key)
        if check is None:
            # Unknown risk — fail open so a forgotten entry doesn't
            # silently disable analysis.
            decisions[risk.key] = True
            continue

        passes = check(snapshot)
        if not passes and use_history:
            passes = await _has_prior_high_risk(
                mt5_login=snapshot.mt5_login, risk_key=risk.key
            )
        decisions[risk.key] = passes

    skipped = [k for k, v in decisions.items() if not v]
    if skipped:
        logger.info(
            "prescreen: login=%s skipped risks=%s", snapshot.mt5_login, skipped
        )
    return decisions
