"""Tests that lock in the additive response shape.

Two guarantees we cannot break (Alex consumes these):
  1. Composite-rule evidence keeps the nested dict under the rule's
     metric name. The flat-sibling promotion is additive: new keys
     appear alongside, the dict itself is unchanged.
  2. `suggested_action` always carries the existing compliance string.
     `dealing_desk_action` is the new optional field — populated only
     for risks where the compliance framing is wrong.
"""

from __future__ import annotations

import pytest

from app.risks import ALL_RISKS, LATENCY_ARBITRAGE, PROFITABLE_CLIENT_PATTERN
from app.schemas import AccountSnapshot
from app.services import analyse_snapshots
from app.services.scoring import dealing_desk_action

from .conftest import canned_response, make_short_trades, make_snapshot_payload


def _seed(evaluator):
    for risk in ALL_RISKS:
        evaluator.responses[risk.key] = canned_response(sub_rules=risk.sub_rules)


# --- dealing_desk_action ----------------------------------------------------


def test_dealing_desk_action_pure_function_compliance_risks_return_none():
    for risk in ALL_RISKS:
        if risk.key == "profitable_client_pattern":
            continue
        for level in ("low", "watch", "medium", "high", "critical"):
            assert dealing_desk_action(risk.key, level) is None, (
                f"{risk.key} at {level} should have no dealing-desk action"
            )


def test_dealing_desk_action_pure_function_profitable_client_pattern():
    assert dealing_desk_action("profitable_client_pattern", "low") is None
    assert dealing_desk_action("profitable_client_pattern", "watch") == "monitor_in_dealing_desk"
    assert dealing_desk_action("profitable_client_pattern", "medium") == "flag_for_a_book_review"
    assert dealing_desk_action("profitable_client_pattern", "high") == "route_to_a_book"
    assert dealing_desk_action("profitable_client_pattern", "critical") == "route_to_a_book_urgent"


@pytest.mark.asyncio
async def test_dealing_desk_action_field_present_on_findings(db, evaluator):
    """Every finding has the field. For compliance risks it is None;
    for profitable_client_pattern at critical it is the A-book string."""
    _seed(evaluator)
    # Build a snapshot that drives profitable_client_pattern to 4/4 (critical).
    trades = []
    for d in range(5):
        for i in range(12):
            trades.append({
                **make_short_trades(1)[0],
                "id": d * 100 + i,
                "open_time": f"2026-05-{15 + d:02d}T10:{i:02d}:00Z",
                "time":      f"2026-05-{15 + d:02d}T10:{i:02d}:30Z",
                "profit":    30.0 if i >= 2 else -60.0,
            })
    snap = AccountSnapshot.model_validate(make_snapshot_payload(
        trades=trades,
        start_time="2026-05-15T00:00:00Z",
        end_time="2026-05-20T00:00:00Z",
    ))

    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=False,
    )

    by_type = {f.risk_type: f for f in findings}
    # Compliance risks: field exists, value is None
    for key in ("latency_arbitrage", "scalping", "swap_arbitrage", "bonus_abuse"):
        assert by_type[key].dealing_desk_action is None, (
            f"{key} should not carry a dealing-desk action"
        )
    # Profitable client at critical: A-book urgent
    pcp = by_type["profitable_client_pattern"]
    assert pcp.risk_level == "critical"
    assert pcp.dealing_desk_action == "route_to_a_book_urgent"


# --- composite evidence flattening (additive) ------------------------------


@pytest.mark.asyncio
async def test_composite_evidence_keeps_nested_dict_and_adds_flat_siblings(db, evaluator):
    """Latency R4 (composite: win_rate >= 0.9 AND batch_close_ratio <= 0.2)
    produces a dict observed_value. The dict must still be reachable under
    `evidence.win_rate` (back-compat with what Alex sees today), AND
    `evidence.batch_close_ratio` must now also be a top-level scalar."""
    _seed(evaluator)
    # 30 short bidirectional all-winning scattered trades → all 4 latency
    # rules trip, R4 returns a dict observed_value.
    trades = make_short_trades(n=30, side="buy", profit=1.0)
    for i in range(0, 30, 2):
        trades[i]["side"] = "sell"
    snap = AccountSnapshot.model_validate(make_snapshot_payload(trades=trades))

    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=False,
    )
    la = next(f for f in findings if f.risk_type == LATENCY_ARBITRAGE.key)

    # The nested dict under `win_rate` is preserved (existing shape).
    assert isinstance(la.evidence["win_rate"], dict)
    assert "win_rate" in la.evidence["win_rate"]
    assert "batch_close_ratio" in la.evidence["win_rate"]

    # The inner scalars are now ALSO flat siblings at the top level.
    assert "batch_close_ratio" in la.evidence
    assert isinstance(la.evidence["batch_close_ratio"], (int, float))
    # The inner `win_rate` does not overwrite the existing dict-typed key.
    assert isinstance(la.evidence["win_rate"], dict)


@pytest.mark.asyncio
async def test_composite_evidence_for_profitable_client_pattern_flattens(db, evaluator):
    """Profitable R2 is `trade_count >= 50 AND profit_factor >= 1.2`.
    The dict goes under `trade_count`; `profit_factor` should appear as
    a flat sibling."""
    _seed(evaluator)
    # 60 trades over 5 days, mostly profitable -> all 4 rules trip
    trades = []
    for d in range(5):
        for i in range(12):
            trades.append({
                **make_short_trades(1)[0],
                "id": d * 100 + i,
                "open_time": f"2026-05-{15 + d:02d}T10:{i:02d}:00Z",
                "time":      f"2026-05-{15 + d:02d}T10:{i:02d}:30Z",
                "profit":    30.0 if i >= 2 else -60.0,
            })
    snap = AccountSnapshot.model_validate(make_snapshot_payload(
        trades=trades,
        start_time="2026-05-15T00:00:00Z",
        end_time="2026-05-20T00:00:00Z",
    ))

    _, findings = await analyse_snapshots(
        snapshots=[snap], evaluator=evaluator, include_history=False,
    )
    pcp = next(f for f in findings if f.risk_type == "profitable_client_pattern")

    # The nested dict under `trade_count` is preserved.
    assert isinstance(pcp.evidence["trade_count"], dict)
    assert pcp.evidence["trade_count"]["trade_count"] == 60
    assert pcp.evidence["trade_count"]["profit_factor"] >= 1.2
    # The `profit_factor` scalar is now also a flat top-level key.
    assert "profit_factor" in pcp.evidence
    assert pcp.evidence["profit_factor"] >= 1.2


# --- back-compat: nothing existing has changed ------------------------------


@pytest.mark.asyncio
async def test_existing_response_keys_unchanged(client, evaluator):
    """All the keys consumers depend on are still present with the same
    shape. The only diff vs the previous response is two new fields:
    `evidence_description_list` (already shipped earlier) and now
    `dealing_desk_action`."""
    _seed(evaluator)
    snap = make_snapshot_payload(mt5_login=70001)
    resp = await client.post("/analyse_risk", json={"snapshots": [snap]})
    assert resp.status_code == 200
    body = resp.json()

    expected_keys = {
        "mt5_login",
        "risk_type",
        "risk_score",
        "risk_level",
        "trigger_type",
        "evidence",
        "evidence_description_list",
        "suggested_action",
        "dealing_desk_action",  # new, additive
        "analysis",
        "behavior_summary",
    }
    for finding in body:
        assert set(finding.keys()) == expected_keys, finding.keys()
        # suggested_action still carries one of the compliance strings.
        assert finding["suggested_action"] in {
            "log_only",
            "add_to_watchlist",
            "manual_review",
            "restrict_opening_pause_withdrawal",
            "restrict_opening_pause_withdrawal_high_priority",
        }
