"""Schema invariants: window filtering in bucket_by_login + extra=forbid on rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    AlexData,
    AlexResponse,
    Bonus,
    Deposit,
    Trade,
    Withdraw,
    bucket_by_login,
)


WINDOW_START = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 5, 8, 5, 59, 59, 999000, tzinfo=timezone.utc)


def _trade(*, login: int, close_time: datetime, open_time: datetime | None = None) -> Trade:
    return Trade(
        id=1,
        login=login,
        group="real\\group-d",
        symbol="XAUUSD",
        volume=0.01,
        side="buy",
        open_time=open_time or close_time - timedelta(seconds=30),
        time=close_time,  # alias → close_time
        open_price=2300.0,
        close_price=2300.5,
        bid_at_open=2299.95,
        ask_at_open=2300.05,
        profit=0.5,
    )


# ---------------------------------------------------------------------------
# Window filtering
# ---------------------------------------------------------------------------


def test_bucket_by_login_drops_events_outside_window():
    response = AlexResponse(
        status=True,
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        data=AlexData(
            deposits=[
                Deposit(id=1, login=1, group="g", time=WINDOW_START - timedelta(seconds=1), profit=10),
                Deposit(id=2, login=1, group="g", time=WINDOW_START + timedelta(minutes=5), profit=10),
            ],
            withdraws=[
                Withdraw(id=3, login=1, group="g", time=WINDOW_END + timedelta(seconds=1), profit=-5),
            ],
            bonus=[
                Bonus(id=4, login=1, group="g", time=WINDOW_START + timedelta(hours=1), profit=50),
            ],
            trades=[
                # close_time outside the window → dropped
                _trade(login=1, close_time=WINDOW_END + timedelta(minutes=1)),
                # close_time inside the window → kept
                _trade(login=1, close_time=WINDOW_START + timedelta(hours=2)),
            ],
        ),
    )

    snaps = bucket_by_login(response)
    assert len(snaps) == 1
    snap = snaps[0]

    # Only the in-window deposit / bonus / trade survived.
    assert len(snap.deposits) == 1
    assert len(snap.withdraws) == 0
    assert len(snap.bonus) == 1
    assert len(snap.trades) == 1


def test_bucket_by_login_uses_envelope_window_on_each_snapshot():
    response = AlexResponse(
        status=True,
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        data=AlexData(
            deposits=[
                Deposit(id=1, login=200001, group="g", time=WINDOW_START + timedelta(minutes=5), profit=10),
            ],
        ),
    )
    snap = bucket_by_login(response)[0]
    assert snap.start_time == WINDOW_START
    assert snap.end_time == WINDOW_END


# ---------------------------------------------------------------------------
# extra="forbid" on inner row models
# ---------------------------------------------------------------------------


def test_trade_rejects_unknown_field():
    """A typo'd field name must fail loudly, not silently default to 0."""
    payload = {
        "id": 1,
        "login": 200001,
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
        # Typo: should be `swaps`. With extra="ignore" this would silently
        # default swaps to 0 and break the swap-arb rules.
        "swaps_total": 12.0,
    }
    with pytest.raises(ValidationError):
        Trade.model_validate(payload)


def test_deposit_rejects_unknown_field():
    payload = {
        "id": 1,
        "login": 1,
        "group": "g",
        "time": "2026-05-08T00:00:00Z",
        "profit": 100,
        "currency": "USD",  # unknown
    }
    with pytest.raises(ValidationError):
        Deposit.model_validate(payload)


# ---------------------------------------------------------------------------
# Trade.entry default
# ---------------------------------------------------------------------------


def test_trade_entry_defaults_to_zero_when_omitted():
    payload = {
        "id": 1,
        "login": 200001,
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
    t = Trade.model_validate(payload)
    assert t.entry == 0
