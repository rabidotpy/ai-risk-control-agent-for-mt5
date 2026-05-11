"""Risk module sanity — keys, rule counts, prompt structure."""

from __future__ import annotations

from app.risks import ALL_RISKS, REPORT_EVALUATION_TOOL


def test_all_risks_have_unique_keys():
    keys = [r.key for r in ALL_RISKS]
    assert len(set(keys)) == len(keys)


def test_each_risk_has_at_least_one_sub_rule():
    for r in ALL_RISKS:
        assert r.num_sub_rules >= 1
        assert r.num_sub_rules == len(r.sub_rules)


def test_each_system_prompt_contains_input_format_and_output_contract():
    for r in ALL_RISKS:
        sp = r.system_prompt
        assert "current_window" in sp
        assert "prior_behavior_summary" in sp
        assert "report_evaluation" in sp
        assert "behavior_summary" in sp


def test_report_evaluation_tool_requires_behavior_summary():
    schema = REPORT_EVALUATION_TOOL["input_schema"]
    assert "behavior_summary" in schema["properties"]
    assert "behavior_summary" in schema["required"]
