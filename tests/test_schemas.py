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
