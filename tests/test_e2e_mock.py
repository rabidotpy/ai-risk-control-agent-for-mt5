"""End-to-end demonstration: rich mock data → engine → expected risk shape.

This test runs the engine against four hand-crafted snapshots — each shaped
to match exactly one risk type's fingerprint — and uses a *rule-evaluating*
fake LLM (not a fixed canned response) that actually computes each rule
from the snapshot data and the wrapped historical_context payload.

Purpose: prove the prompt → tool → engine → score pipeline is correct
end-to-end without network calls. The same calculations the prompt asks
Claude to perform are implemented in `_evaluate_*` below; if those agree
with what Claude does in production, the production output matches this
test's expected output.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from typing import Any

from app.engine import analyse
from app.risks import (
    ALL_RISKS,
    BONUS_ABUSE,
    LATENCY_ARBITRAGE,
    SCALPING,
    SWAP_ARBITRAGE,
    Risk,
)
from app.schemas import AccountSnapshot

from .fixtures import (
    build_bonus_abuse_snapshot,
    build_latency_arb_snapshot,
    build_scalping_snapshot,
    build_swap_arb_snapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _holding(t) -> float:
    return (t.close_time - t.open_time).total_seconds()


def _favourable(t) -> bool:
    if t.side == "buy":
        return t.open_price < t.ask_at_open
    return t.open_price > t.bid_at_open


def _price_pnl(t) -> float:
    return t.profit - t.swaps - t.commission


def _trend_eval(historical_context: dict | None, risk_key: str) -> dict[str, Any]:
    """Common trend-rule evaluator shared by every risk."""
    rule = "prior_high_or_critical_in_last_5_scans >= 3"
    if not historical_context:
        return {"rule": rule, "observed_value": None, "true": False, "reason": "insufficient_data"}
    trend = (historical_context.get("trend_by_risk") or {}).get(risk_key) or {}
    if trend.get("scans_observed", 0) == 0:
        return {"rule": rule, "observed_value": None, "true": False, "reason": "insufficient_data"}
    count = int(trend.get("prior_high_or_critical_count", 0))
    return {"rule": rule, "observed_value": count, "true": count >= 3, "reason": ""}


# ---------------------------------------------------------------------------
# Per-risk evaluators
# ---------------------------------------------------------------------------


def _evaluate_latency(snap: AccountSnapshot, hist: dict | None) -> dict[str, Any]:
    trades = snap.trades
    n = len(trades)
    evals = []
    evals.append({"rule": "trade_count_6h >= 30", "observed_value": n, "true": n >= 30, "reason": ""})
    if n == 0:
        evals.append({"rule": "median_holding_time_seconds <= 30", "observed_value": None, "true": False, "reason": "insufficient_data"})
        evals.append({"rule": "positive_slippage_ratio >= 0.5", "observed_value": None, "true": False, "reason": "insufficient_data"})
        evals.append({"rule": "short_holding_ratio_30s >= 0.6", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        median = statistics.median(_holding(t) for t in trades)
        fav = sum(1 for t in trades if _favourable(t)) / n
        short = sum(1 for t in trades if _holding(t) <= 30) / n
        evals.append({"rule": "median_holding_time_seconds <= 30", "observed_value": median, "true": median <= 30, "reason": ""})
        evals.append({"rule": "positive_slippage_ratio >= 0.5", "observed_value": fav, "true": fav >= 0.5, "reason": ""})
        evals.append({"rule": "short_holding_ratio_30s >= 0.6", "observed_value": short, "true": short >= 0.6, "reason": ""})
    evals.append(_trend_eval(hist, "latency_arbitrage"))
    return {"evaluations": evals, "summary": "computed"}


def _evaluate_scalping(snap: AccountSnapshot, hist: dict | None) -> dict[str, Any]:
    trades = snap.trades
    n = len(trades)
    evals = []
    # R1 reads from historical_context.lookbacks.trade_count_24h.
    lookbacks = (hist or {}).get("lookbacks") or {}
    tc24 = lookbacks.get("trade_count_24h")
    if tc24 is None:
        evals.append({"rule": "trade_count_24h >= 100", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        evals.append({"rule": "trade_count_24h >= 100", "observed_value": tc24, "true": tc24 >= 100, "reason": ""})
    if n == 0:
        evals.append({"rule": "short_holding_ratio_60s >= 0.7", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        short = sum(1 for t in trades if _holding(t) <= 60) / n
        evals.append({"rule": "short_holding_ratio_60s >= 0.7", "observed_value": short, "true": short >= 0.7, "reason": ""})
    if n < 5:
        evals.append({"rule": "win_rate >= 0.75", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        win = sum(1 for t in trades if t.profit > 0) / n
        evals.append({"rule": "win_rate >= 0.75", "observed_value": win, "true": win >= 0.75, "reason": ""})
    if n < 3:
        evals.append({"rule": "repeated_lot_sl_tp_pattern_ratio >= 0.5", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        buckets = Counter((t.volume, t.stop_loss or 0, t.take_profit or 0) for t in trades)
        pattern = sum(c for c in buckets.values() if c >= 3) / n
        evals.append({"rule": "repeated_lot_sl_tp_pattern_ratio >= 0.5", "observed_value": pattern, "true": pattern >= 0.5, "reason": ""})
    evals.append(_trend_eval(hist, "scalping"))
    return {"evaluations": evals, "summary": "computed"}


def _evaluate_swap(snap: AccountSnapshot, hist: dict | None) -> dict[str, Any]:
    trades = snap.trades
    n = len(trades)
    evals = []
    total_swap = sum(t.swaps for t in trades)
    total_profit = sum(t.profit for t in trades)
    if total_profit > 0:
        ratio = total_swap / total_profit
        evals.append({"rule": "swap_profit_ratio >= 0.6", "observed_value": ratio, "true": ratio >= 0.6, "reason": ""})
    else:
        evals.append({"rule": "swap_profit_ratio >= 0.6", "observed_value": None, "true": False, "reason": "insufficient_data"})

    if n == 0:
        evals.append({"rule": "positions_held_across_rollover >= 1", "observed_value": None, "true": False, "reason": "insufficient_data"})
        evals.append({"rule": "swap_dominant_closed_positions >= 5", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        rollover = sum(1 for t in trades if t.open_time.date() != t.close_time.date())
        evals.append({"rule": "positions_held_across_rollover >= 1", "observed_value": rollover, "true": rollover >= 1, "reason": ""})
        dominant = sum(
            1 for t in trades
            if t.swaps > 0 and abs(_price_pnl(t)) <= 0.1 * t.swaps
        )
        evals.append({"rule": "swap_dominant_closed_positions >= 5", "observed_value": dominant, "true": dominant >= 5, "reason": ""})

    pos_swap_trades = [t for t in trades if t.swaps > 0]
    total_pos_swap = sum(t.swaps for t in pos_swap_trades)
    if total_pos_swap > 0:
        total_price = sum(_price_pnl(t) for t in pos_swap_trades)
        ratio = total_price / total_pos_swap
        evals.append({"rule": "average_price_movement_pnl_low", "observed_value": ratio, "true": -0.2 <= ratio <= 0.2, "reason": ""})
    else:
        evals.append({"rule": "average_price_movement_pnl_low", "observed_value": None, "true": False, "reason": "insufficient_data"})

    evals.append(_trend_eval(hist, "swap_arbitrage"))
    return {"evaluations": evals, "summary": "computed"}


def _evaluate_bonus(snap: AccountSnapshot, hist: dict | None) -> dict[str, Any]:
    bonus = snap.bonus
    linked = snap.linked_accounts
    lookbacks = (hist or {}).get("lookbacks") or {}
    most_recent_bonus = lookbacks.get("most_recent_bonus_time")
    evals = []

    evals.append({"rule": "bonus_received_in_window", "observed_value": len(bonus), "true": len(bonus) >= 1, "reason": ""})

    if not most_recent_bonus:
        evals.append({"rule": "trades_within_24h_after_bonus >= 30", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        v = lookbacks.get("trades_within_24h_after_bonus", 0)
        evals.append({"rule": "trades_within_24h_after_bonus >= 30", "observed_value": v, "true": v >= 30, "reason": ""})

    evals.append({"rule": "linked_account_count >= 2", "observed_value": len(linked), "true": len(linked) >= 2, "reason": ""})
    opp = sum(1 for la in linked if la.opposing_trade_count >= 1)
    evals.append({"rule": "linked_with_opposing_trades >= 1", "observed_value": opp, "true": opp >= 1, "reason": ""})

    if not most_recent_bonus:
        evals.append({"rule": "withdrawal_within_72h_of_bonus", "observed_value": None, "true": False, "reason": "insufficient_data"})
    else:
        v = bool(lookbacks.get("withdrawal_within_72h_of_bonus"))
        observed = lookbacks.get("hours_bonus_to_withdrawal")
        evals.append({"rule": "withdrawal_within_72h_of_bonus", "observed_value": observed, "true": v, "reason": ""})

    evals.append(_trend_eval(hist, "bonus_abuse"))
    return {"evaluations": evals, "summary": "computed"}


_DISPATCH = {
    "latency_arbitrage": _evaluate_latency,
    "scalping": _evaluate_scalping,
    "swap_arbitrage": _evaluate_swap,
    "bonus_abuse": _evaluate_bonus,
}


class RuleEvaluatingEvaluator:
    """Fake evaluator that parses the wrapped payload + computes rules from it.

    Mirrors the contract the engine sends to the LLM: the user message is
    `{"current_window": <snapshot>, "historical_context": <ctx | null>}`.
    """

    def __init__(self, snapshot: AccountSnapshot):
        self._snap = snapshot
        self.calls: list[str] = []

    def evaluate(self, risk: Risk, payload_json: str) -> dict[str, Any]:
        self.calls.append(risk.key)
        payload = json.loads(payload_json)
        # Sanity: the wrapped envelope is what production sends.
        assert "current_window" in payload, "engine must wrap payload"
        assert "historical_context" in payload, "engine must wrap payload"
        hist = payload["historical_context"]
        return _DISPATCH[risk.key](self._snap, hist)


# ---------------------------------------------------------------------------
# Historical-context fixtures — synthesise the long-window counters that
# Phase B aggregator would have produced, so the assertions stay focused on
# the "this fingerprint trips this risk" property rather than on cache state.
# ---------------------------------------------------------------------------


def _trend_block(repeat: bool = True) -> dict[str, Any]:
    """Trend block for one risk type — fires when repeat=True."""
    if repeat:
        return {"prior_scores": [80, 85, 90, 78, 82], "prior_high_or_critical_count": 5, "scans_observed": 5}
    return {"prior_scores": [10, 0, 20, 5, 10], "prior_high_or_critical_count": 0, "scans_observed": 5}


def _hist_for(snap: AccountSnapshot, *, repeat_for: str | None) -> dict[str, Any]:
    """Build a historical_context where only `repeat_for` shows the trend."""
    trade_count_24h = len(snap.trades) * 4  # ~four 6h windows of the same density
    most_recent_bonus = max((b.time for b in snap.bonus), default=None)
    if most_recent_bonus is not None:
        trades_after = sum(1 for t in snap.trades if t.open_time >= most_recent_bonus)
        # Scale the 6h count up to a 24h estimate.
        trades_within_24h_after_bonus = trades_after * 4
        candidates = sorted(w.time for w in snap.withdraws if w.time >= most_recent_bonus)
        if candidates:
            hours = (candidates[0] - most_recent_bonus).total_seconds() / 3600
            withdrawal_within_72h_of_bonus = hours <= 72
            hours_to_w = round(hours, 2)
        else:
            # Synthesise a clean within-72h withdrawal so R5 fires for the bonus fixture.
            withdrawal_within_72h_of_bonus = True
            hours_to_w = 12.0
    else:
        trades_within_24h_after_bonus = 0
        withdrawal_within_72h_of_bonus = False
        hours_to_w = None

    return {
        "lookbacks": {
            "trade_count_24h": trade_count_24h,
            "trade_count_30d": trade_count_24h * 30,
            "bonus_count_30d": len(snap.bonus),
            "most_recent_bonus_time": most_recent_bonus.isoformat() if most_recent_bonus else None,
            "trades_within_24h_after_bonus": trades_within_24h_after_bonus,
            "withdrawal_within_72h_of_bonus": withdrawal_within_72h_of_bonus,
            "hours_bonus_to_withdrawal": hours_to_w,
            "raw_pulls_used": 4,
        },
        "trend_by_risk": {
            "latency_arbitrage": _trend_block(repeat_for == "latency_arbitrage"),
            "scalping":          _trend_block(repeat_for == "scalping"),
            "swap_arbitrage":    _trend_block(repeat_for == "swap_arbitrage"),
            "bonus_abuse":       _trend_block(repeat_for == "bonus_abuse"),
        },
    }


# ---------------------------------------------------------------------------
# End-to-end assertions
# ---------------------------------------------------------------------------


def _by_key(results):
    return {r.risk_type: r for r in results}


def test_latency_arb_snapshot_scores_critical_on_latency_only():
    snap = build_latency_arb_snapshot()
    hist = _hist_for(snap, repeat_for="latency_arbitrage")
    results = analyse(snap, RuleEvaluatingEvaluator(snap), historical_context=hist)
    by_key = _by_key(results)

    # Latency: all 5 rules fire (4 base + trend) → 100 / critical
    assert by_key["latency_arbitrage"].risk_score == 100
    assert by_key["latency_arbitrage"].risk_level == "critical"
    # NOTE: latency-arb and scalping fingerprints intentionally overlap — the
    # PRD §7.2 alert example explicitly shows "Latency Arbitrage + Scalping
    # Pattern" co-firing. We assert here that swap and bonus do NOT misfire.
    assert by_key["swap_arbitrage"].risk_score == 0
    assert by_key["bonus_abuse"].risk_score < 60


def test_scalping_snapshot_scores_high_on_scalping():
    snap = build_scalping_snapshot()
    hist = _hist_for(snap, repeat_for="scalping")
    by_key = _by_key(analyse(snap, RuleEvaluatingEvaluator(snap), historical_context=hist))

    # Scalping: all 5 rules fire (R1 via trade_count_24h, R2/R3/R4 from window, trend) → 100 / critical
    assert by_key["scalping"].risk_score == 100
    assert by_key["scalping"].risk_level == "critical"
    # Bonus shouldn't trigger heavily
    assert by_key["bonus_abuse"].risk_score < 60


def test_swap_arb_snapshot_scores_critical_on_swap():
    snap = build_swap_arb_snapshot()
    hist = _hist_for(snap, repeat_for="swap_arbitrage")
    by_key = _by_key(analyse(snap, RuleEvaluatingEvaluator(snap), historical_context=hist))

    # Swap arb: at minimum R1 (swap_profit_ratio), R3 (≥5 dominant),
    # R4 (price pnl low), plus trend = 4/5 = 80. Rollover R2 only fires if
    # open/close span midnight, which our fixture controls.
    swap = by_key["swap_arbitrage"]
    assert swap.risk_score >= 75
    assert swap.risk_level in ("high", "critical")


def test_bonus_abuse_snapshot_scores_critical_on_bonus():
    snap = build_bonus_abuse_snapshot()
    hist = _hist_for(snap, repeat_for="bonus_abuse")
    by_key = _by_key(analyse(snap, RuleEvaluatingEvaluator(snap), historical_context=hist))

    bonus = by_key["bonus_abuse"]
    # All 6 bonus rules fire (R1 in-window, R2 24h-aggregate, R3/R4 linked, R5 72h, trend) → 100
    assert bonus.risk_score == 100
    assert bonus.risk_level == "critical"
    assert bonus.suggested_action == "restrict_opening_pause_withdrawal_high_priority"
    # Trigger type should propagate
    assert bonus.trigger_type == "withdrawal_request"


def test_engine_runs_all_four_risks_per_snapshot():
    snap = build_latency_arb_snapshot()
    ev = RuleEvaluatingEvaluator(snap)
    results = analyse(snap, ev)

    assert len(results) == 4
    assert sorted(ev.calls) == sorted(r.key for r in ALL_RISKS)


