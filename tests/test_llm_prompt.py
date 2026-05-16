"""Prompt builder."""

from __future__ import annotations

import json

from app.llm import build_user_payload
from app.schemas import AccountSnapshot

from .conftest import make_snapshot_payload


def _snap() -> AccountSnapshot:
    return AccountSnapshot.model_validate(make_snapshot_payload())


def test_payload_has_three_top_level_keys():
    payload = build_user_payload(_snap(), prior_behavior_summary=None)
    obj = json.loads(payload)
    assert set(obj.keys()) == {
        "current_window",
        "rule_outcomes",
        "prior_behavior_summary",
    }
    assert obj["prior_behavior_summary"] is None
    assert obj["rule_outcomes"] == []


def test_payload_carries_rule_outcomes():
    from app.rules.types import RuleOutcome

    outcomes = [
        RuleOutcome(rule="trade_count_in_window >= 30", observed_value=42, true=True, reason="42 trades"),
    ]
    payload = build_user_payload(
        _snap(), prior_behavior_summary=None, rule_outcomes=outcomes
    )
    obj = json.loads(payload)
    assert obj["rule_outcomes"] == [
        {"rule": "trade_count_in_window >= 30", "observed_value": 42, "true": True, "reason": "42 trades"}
    ]


def test_payload_carries_prior_summary_verbatim():
    prior = {"run_count": 5, "severity_trend": "stable", "notes": "occasional bursts"}
    payload = build_user_payload(_snap(), prior_behavior_summary=prior)
    obj = json.loads(payload)
    assert obj["prior_behavior_summary"] == prior


def test_payload_serialises_close_time_not_alias():
    payload = build_user_payload(
        AccountSnapshot.model_validate(
            make_snapshot_payload(
                trades=[
                    {
                        "id": 1,
                        "login": 70001,
                        "group": "g",
                        "symbol": "XAUUSD",
                        "volume": 0.01,
                        "side": "buy",
                        "open_time": "2026-05-08T00:00:00Z",
                        "time": "2026-05-08T00:00:30Z",
                        "open_price": 2300.0,
                        "close_price": 2300.5,
                        "bid_at_open": 2299.95,
                        "ask_at_open": 2300.05,
                        "profit": 0.5,
                    }
                ]
            )
        ),
        prior_behavior_summary=None,
    )
    obj = json.loads(payload)
    trade = obj["current_window"]["trades"][0]
    assert "close_time" in trade
    assert "time" not in trade
