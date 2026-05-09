"""Engine: per-risk LLM calls, score math, banding, evidence, defensive parsing."""

from __future__ import annotations

import pytest

from app.engine import (
    _build_result,
    _metric_name,
    analyse,
    level_to_action,
    score_to_level,
)
from app.risks import (
    ALL_RISKS,
    BONUS_ABUSE,
    LATENCY_ARBITRAGE,
    SCALPING,
    SWAP_ARBITRAGE,
)

from .conftest import FakeEvaluator
from .fixtures import all_false, all_true, first_n_true, sample_snapshot


# ---------------------------------------------------------------------------
# Banding + suggested_action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score, level",
    [
        (0, "low"),
        (39, "low"),
        (40, "watch"),
        (59, "watch"),
        (60, "medium"),
        (74, "medium"),
        (75, "high"),
        (89, "high"),
        (90, "critical"),
        (100, "critical"),
    ],
)
def test_score_to_level(score, level):
    assert score_to_level(score) == level


def test_level_to_action_mapping():
    assert level_to_action("low") == "log_only"
    assert level_to_action("watch") == "add_to_watchlist"
    assert level_to_action("medium") == "manual_review"
    assert level_to_action("high") == "restrict_opening_pause_withdrawal"
    assert level_to_action("critical") == "restrict_opening_pause_withdrawal_high_priority"


# ---------------------------------------------------------------------------
# metric name extraction (for evidence dict keys)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule, expected",
    [
        ("trade_count_6h >= 30", "trade_count_6h"),
        ("median_holding_time_seconds <= 30", "median_holding_time_seconds"),
        ("win_rate >= 0.75", "win_rate"),
        ("repeated_lot_sl_tp_pattern_ratio >= 0.5", "repeated_lot_sl_tp_pattern_ratio"),
        ("bonus_received_in_window", "bonus_received_in_window"),
    ],
)
def test_metric_name_extraction(rule, expected):
    assert _metric_name(rule) == expected


# ---------------------------------------------------------------------------
# End-to-end engine behaviour against the fake evaluator
# ---------------------------------------------------------------------------


def test_all_true_yields_full_score_per_risk():
    evaluator = FakeEvaluator()
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    results = analyse(sample_snapshot(), evaluator)

    assert len(results) == 4
    by_key = {r.risk_type: r for r in results}
    for risk in ALL_RISKS:
        r = by_key[risk.key]
        assert r.risk_score == 100
        assert r.risk_level == "critical"
        assert r.suggested_action == "restrict_opening_pause_withdrawal_high_priority"
        assert r.mt5_login == 200001
        assert r.trigger_type == "scheduled_scan"


def test_all_false_yields_zero_score_and_low_level():
    evaluator = FakeEvaluator()
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_false(risk))

    for r in analyse(sample_snapshot(), evaluator):
        assert r.risk_score == 0
        assert r.risk_level == "low"
        assert r.suggested_action == "log_only"


def test_partial_score_maps_to_correct_level():
    """Verify the score → level → action chain for partial matches.

    Phase B: every risk now has the trend rule appended, so denominators
    are 5 (latency / scalping / swap_arb) and 6 (bonus_abuse).
    """

    evaluator = FakeEvaluator()
    # latency arb: 4/5 = 80 → high
    evaluator.set(LATENCY_ARBITRAGE.key, first_n_true(LATENCY_ARBITRAGE, 4))
    # scalping: 2/5 = 40 → watch
    evaluator.set(SCALPING.key, first_n_true(SCALPING, 2))
    # swap arb: 0/5 = 0 → low
    evaluator.set(SWAP_ARBITRAGE.key, first_n_true(SWAP_ARBITRAGE, 0))
    # bonus: 4/6 ≈ 67 → medium
    evaluator.set(BONUS_ABUSE.key, first_n_true(BONUS_ABUSE, 4))

    by_key = {r.risk_type: r for r in analyse(sample_snapshot(), evaluator)}

    assert by_key["latency_arbitrage"].risk_score == 80
    assert by_key["latency_arbitrage"].risk_level == "high"
    assert (
        by_key["latency_arbitrage"].suggested_action
        == "restrict_opening_pause_withdrawal"
    )

    assert by_key["scalping"].risk_score == 40
    assert by_key["scalping"].risk_level == "watch"
    assert by_key["scalping"].suggested_action == "add_to_watchlist"

    assert by_key["swap_arbitrage"].risk_score == 0
    assert by_key["swap_arbitrage"].risk_level == "low"

    assert by_key["bonus_abuse"].risk_score == 67
    assert by_key["bonus_abuse"].risk_level == "medium"
    assert by_key["bonus_abuse"].suggested_action == "manual_review"


def test_evidence_dict_keyed_by_metric_name():
    evaluator = FakeEvaluator()
    evaluator.set(LATENCY_ARBITRAGE.key, all_true(LATENCY_ARBITRAGE))
    for risk in (SCALPING, SWAP_ARBITRAGE, BONUS_ABUSE):
        evaluator.set(risk.key, all_false(risk))

    by_key = {r.risk_type: r for r in analyse(sample_snapshot(), evaluator)}
    evidence = by_key["latency_arbitrage"].evidence

    # Keys are derived from rule text — operators stripped.
    assert "trade_count_6h" in evidence
    assert "median_holding_time_seconds" in evidence
    assert "positive_slippage_ratio" in evidence
    assert "short_holding_ratio_30s" in evidence
    # observed_value=1 for all_true fixture
    assert all(v == 1 for v in evidence.values())


def test_engine_calls_evaluator_once_per_risk():
    evaluator = FakeEvaluator()
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_false(risk))

    analyse(sample_snapshot(), evaluator)

    keys_called = sorted(c[0] for c in evaluator.calls)
    assert keys_called == [
        "bonus_abuse",
        "latency_arbitrage",
        "scalping",
        "swap_arbitrage",
    ]


# ---------------------------------------------------------------------------
# Defensive parsing
# ---------------------------------------------------------------------------


def test_unknown_rule_text_is_ignored():
    rogue_payload = {
        "evaluations": [
            {"rule": "made_up_rule_not_in_prompt", "true": True, "reason": "fixture"},
            {
                "rule": LATENCY_ARBITRAGE.sub_rules[0],
                "observed_value": 86,
                "true": True,
                "reason": "fixture",
            },
        ],
        "summary": "rogue",
    }
    result = _build_result(
        risk=LATENCY_ARBITRAGE,
        tool_input=rogue_payload,
        mt5_login=123456,
        trigger_type="scheduled_scan",
    )
    assert result.risk_score == 20
    assert "trade_count_6h" in result.evidence
    assert "made_up_rule_not_in_prompt" not in result.evidence


def test_duplicate_rule_text_counted_once():
    duplicate_payload = {
        "evaluations": [
            {
                "rule": LATENCY_ARBITRAGE.sub_rules[0],
                "observed_value": 86,
                "true": True,
                "reason": "first",
            },
            {
                "rule": LATENCY_ARBITRAGE.sub_rules[0],
                "observed_value": 86,
                "true": True,
                "reason": "again",
            },
        ],
        "summary": "dup",
    }
    result = _build_result(
        risk=LATENCY_ARBITRAGE,
        tool_input=duplicate_payload,
        mt5_login=123456,
        trigger_type="scheduled_scan",
    )
    assert result.risk_score == 20


def test_missing_evaluations_field_yields_zero():
    result = _build_result(
        risk=LATENCY_ARBITRAGE,
        tool_input={"summary": "weird"},
        mt5_login=123456,
        trigger_type="scheduled_scan",
    )
    assert result.risk_score == 0
    assert result.risk_level == "low"
    assert result.evidence == {}
    assert result.analysis == "weird"


def test_summary_passes_through_as_analysis():
    payload = all_true(LATENCY_ARBITRAGE, summary="A latency-arb pattern is evident.")
    result = _build_result(
        risk=LATENCY_ARBITRAGE,
        tool_input=payload,
        mt5_login=123456,
        trigger_type="scheduled_scan",
    )
    assert result.analysis == "A latency-arb pattern is evident."


# ---------------------------------------------------------------------------
# Per-risk error containment
# ---------------------------------------------------------------------------


class _ExplodingEvaluator:
    """Raises for one risk key; returns all-true for the rest."""

    def __init__(self, raising_key: str):
        self._raising = raising_key

    def evaluate(self, risk, payload_json):
        if risk.key == self._raising:
            raise RuntimeError("simulated upstream failure")
        return all_true(risk)


def test_one_risk_failure_does_not_lose_other_results():
    """A network blip on one Claude call must NOT lose the other 3 analyses."""

    evaluator = _ExplodingEvaluator(raising_key=LATENCY_ARBITRAGE.key)
    results = analyse(sample_snapshot(), evaluator)

    # Still 4 rows, one per risk.
    assert len(results) == 4
    by_key = {r.risk_type: r for r in results}

    # The errored risk is recorded as a zero-score row tagged with the cause.
    err = by_key["latency_arbitrage"]
    assert err.risk_score == 0
    assert err.risk_level == "low"
    assert "RuntimeError" in err.evidence.get("error", "")
    assert err.analysis.startswith("error:")

    # The other three completed normally.
    for key in ("scalping", "swap_arbitrage", "bonus_abuse"):
        assert by_key[key].risk_score == 100


def test_insufficient_data_observed_value_skipped_from_evidence():
    payload = {
        "evaluations": [
            {
                "rule": LATENCY_ARBITRAGE.sub_rules[0],
                "observed_value": 86,
                "true": True,
                "reason": "ok",
            },
            {
                "rule": LATENCY_ARBITRAGE.sub_rules[1],
                "observed_value": None,
                "true": False,
                "reason": "insufficient_data: no closed positions",
            },
        ],
        "summary": "partial",
    }
    result = _build_result(
        risk=LATENCY_ARBITRAGE,
        tool_input=payload,
        mt5_login=123456,
        trigger_type="scheduled_scan",
    )
    # Only the rule with a non-null observed_value lands in evidence.
    assert "trade_count_6h" in result.evidence
    assert "median_holding_time" not in result.evidence
