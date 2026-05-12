"""Tests for the per-account high-risk filter."""

from __future__ import annotations

from app.schemas import RiskFinding
from app.services.filtering import filter_high_risk_accounts


def _finding(*, login: int, risk_type: str, score: int) -> RiskFinding:
    level = "high" if score >= 80 else "medium" if score >= 60 else "low"
    return RiskFinding(
        mt5_login=login,
        risk_type=risk_type,
        risk_score=score,
        risk_level=level,
        trigger_type="manual_run",
        evidence={},
        suggested_action="alert",
        analysis="x",
        behavior_summary=None,
    )


def test_empty_input_returns_empty():
    assert filter_high_risk_accounts([], min_score=60) == []


def test_low_score_account_dropped():
    findings = [
        _finding(login=1, risk_type="latency_arbitrage", score=10),
        _finding(login=1, risk_type="scalping", score=20),
    ]
    assert filter_high_risk_accounts(findings, min_score=60) == []


def test_high_score_account_kept():
    findings = [
        _finding(login=1, risk_type="latency_arbitrage", score=80),
        _finding(login=1, risk_type="scalping", score=10),
    ]
    kept = filter_high_risk_accounts(findings, min_score=60)
    # Per-account semantics: BOTH rows for the kept account survive.
    assert [f.risk_type for f in kept] == ["latency_arbitrage", "scalping"]


def test_per_account_filtering_preserves_input_order():
    findings = [
        _finding(login=1, risk_type="latency_arbitrage", score=10),  # drop
        _finding(login=2, risk_type="latency_arbitrage", score=70),  # keep
        _finding(login=1, risk_type="scalping", score=20),           # drop
        _finding(login=2, risk_type="scalping", score=10),           # keep (login 2)
        _finding(login=3, risk_type="latency_arbitrage", score=90),  # keep
    ]
    kept = filter_high_risk_accounts(findings, min_score=60)
    assert [(f.mt5_login, f.risk_type) for f in kept] == [
        (2, "latency_arbitrage"),
        (2, "scalping"),
        (3, "latency_arbitrage"),
    ]


def test_threshold_is_inclusive():
    findings = [_finding(login=1, risk_type="scalping", score=60)]
    assert len(filter_high_risk_accounts(findings, min_score=60)) == 1


def test_zero_threshold_keeps_everything():
    findings = [_finding(login=1, risk_type="scalping", score=0)]
    assert len(filter_high_risk_accounts(findings, min_score=0)) == 1
