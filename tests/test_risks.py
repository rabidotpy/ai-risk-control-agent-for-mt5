"""Sanity checks on the four risk definitions and their system prompts."""

from __future__ import annotations

import pytest

from app.risks import (
    ALL_RISKS,
    BONUS_ABUSE,
    LATENCY_ARBITRAGE,
    REPORT_EVALUATION_TOOL,
    SCALPING,
    SWAP_ARBITRAGE,
)


def test_exactly_four_risks_registered():
    assert len(ALL_RISKS) == 4
    keys = {r.key for r in ALL_RISKS}
    assert keys == {"latency_arbitrage", "scalping", "swap_arbitrage", "bonus_abuse"}


@pytest.mark.parametrize(
    "risk, expected_n",
    [
        # Phase B: every risk gets the shared trend rule appended
        # (`prior_high_or_critical_in_last_5_scans >= 3`).
        (LATENCY_ARBITRAGE, 5),
        (SCALPING, 5),
        (SWAP_ARBITRAGE, 5),
        (BONUS_ABUSE, 6),  # bonus abuse: 5 base + 1 trend
    ],
)
def test_sub_rule_counts(risk, expected_n):
    assert risk.num_sub_rules == expected_n
    assert len(risk.sub_rules) == expected_n


def test_every_risk_includes_trend_rule_last():
    from app.risks.base import TREND_RULE

    for risk in ALL_RISKS:
        assert risk.sub_rules[-1] == TREND_RULE, risk.key


def test_each_risk_prompt_mentions_every_sub_rule_verbatim():
    for risk in ALL_RISKS:
        for rule in risk.sub_rules:
            assert rule in risk.system_prompt, (
                f"{risk.key}: prompt missing rule text '{rule}'"
            )


def test_each_risk_prompt_includes_input_preamble():
    for risk in ALL_RISKS:
        # Sentinel string from base.INPUT_PREAMBLE
        assert "DERIVED FACTS" in risk.system_prompt, risk.key
        assert "report_evaluation" in risk.system_prompt, risk.key


def test_report_evaluation_tool_schema_shape():
    assert REPORT_EVALUATION_TOOL["name"] == "report_evaluation"
    schema = REPORT_EVALUATION_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert "evaluations" in schema["properties"]
    assert "summary" in schema["properties"]
