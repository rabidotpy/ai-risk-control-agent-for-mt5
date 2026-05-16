"""Schema-level tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import AccountSnapshot, Deposit, Trade


def _trade_payload(**overrides):
    base = {
        "id": 1,
        "login": 70001,
        "group": "real\\group-d",
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
    base.update(overrides)
    return base


def test_trade_uses_time_alias_for_close_time():
    t = Trade.model_validate(_trade_payload())
    assert t.close_time.isoformat().startswith("2026-05-08T00:00:30")


def test_trade_rejects_unknown_field():
    with pytest.raises(ValidationError):
        Trade.model_validate(_trade_payload(swaps_total=12.0))


def test_trade_entry_defaults_to_zero():
    assert Trade.model_validate(_trade_payload()).entry == 0


def test_trade_comment_defaults_to_empty():
    assert Trade.model_validate(_trade_payload()).comment == ""


def test_trade_accepts_broker_comment_string():
    t = Trade.model_validate(_trade_payload(comment="XAUUSD 5 Minute"))
    assert t.comment == "XAUUSD 5 Minute"


def test_deposit_rejects_unknown_field():
    payload = {
        "id": 1,
        "login": 70001,
        "group": "g",
        "time": "2026-05-08T00:00:00Z",
        "profit": 100,
        "currency": "USD",  # unknown
    }
    with pytest.raises(ValidationError):
        Deposit.model_validate(payload)


def test_account_snapshot_defaults_empty_arrays():
    snap = AccountSnapshot.model_validate(
        {
            "mt5_login": 70001,
            "start_time": "2026-05-08T00:00:00Z",
            "end_time": "2026-05-08T05:59:59Z",
        }
    )
    assert snap.trades == [] and snap.bonus == [] and snap.linked_accounts == []


# --- Envelope normalisation ---------------------------------------------------


def _bare_snapshot():
    return {
        "mt5_login": 250030,
        "trigger_type": "scheduled_scan",
        "start_time": "2026-05-14T20:00:00Z",
        "end_time": "2026-05-14T22:00:00Z",
        "trades": [],
        "deposits": [],
        "withdraws": [],
        "bonus": [],
        "linked_accounts": [],
    }


def test_envelope_accepts_canonical_list():
    from app.schemas.analysis import AnalyseRiskRequest

    req = AnalyseRiskRequest.model_validate({"snapshots": [_bare_snapshot()]})
    assert len(req.snapshots) == 1
    assert req.snapshots[0].mt5_login == 250030


def test_envelope_accepts_singular_snapshot_alias():
    from app.schemas.analysis import AnalyseRiskRequest

    req = AnalyseRiskRequest.model_validate({"snapshot": _bare_snapshot()})
    assert len(req.snapshots) == 1
    assert req.snapshots[0].mt5_login == 250030


def test_envelope_accepts_bare_object_under_snapshots_key():
    """The mistake the manual UI repeatedly made: {"snapshots": {obj}}."""
    from app.schemas.analysis import AnalyseRiskRequest

    req = AnalyseRiskRequest.model_validate({"snapshots": _bare_snapshot()})
    assert len(req.snapshots) == 1
    assert req.snapshots[0].mt5_login == 250030


def test_envelope_still_rejects_unknown_top_level_key():
    from app.schemas.analysis import AnalyseRiskRequest

    with pytest.raises(ValidationError):
        AnalyseRiskRequest.model_validate(
            {"snapshots": [_bare_snapshot()], "totally_unknown_field": 1}
        )
