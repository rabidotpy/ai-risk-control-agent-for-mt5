"""Tests for the cheap pre-LLM gate."""

from __future__ import annotations

import pytest

from app.config import settings
from app.schemas import AccountSnapshot
from app.services.prescreen import prescreen_snapshot

from .conftest import make_snapshot_payload


def _snapshot(**kw) -> AccountSnapshot:
    return AccountSnapshot.model_validate(make_snapshot_payload(**kw))


@pytest.fixture(autouse=True)
def _enable_prescreen(monkeypatch):
    monkeypatch.setattr(settings, "prescreen_enabled", True)


@pytest.mark.asyncio
async def test_disabled_means_every_risk_passes(monkeypatch):
    monkeypatch.setattr(settings, "prescreen_enabled", False)
    snap = _snapshot()  # empty snapshot
    decisions = await prescreen_snapshot(snap, use_history=False)
    assert all(decisions.values())


@pytest.mark.asyncio
async def test_empty_snapshot_skips_every_risk():
    snap = _snapshot()
    decisions = await prescreen_snapshot(snap, use_history=False)
    assert decisions == {
        "latency_arbitrage": False,
        "scalping": False,
        "swap_arbitrage": False,
        "bonus_abuse": False,
    }


def _trade(i: int, *, swaps: float = 0.0) -> dict:
    return {
        "id": i,
        "login": 80101,
        "group": "real\\A",
        "symbol": "EURUSD",
        "volume": 0.1,
        "side": "buy",
        "open_time": "2026-05-08T00:00:00Z",
        "time": "2026-05-08T00:00:30Z",
        "open_price": 1.085,
        "close_price": 1.086,
        "bid_at_open": 1.0849,
        "ask_at_open": 1.0851,
        "swaps": swaps,
        "profit": 1.0,
    }


@pytest.mark.asyncio
async def test_high_trade_count_passes_latency_and_scalping():
    snap = _snapshot(trades=[_trade(i) for i in range(25)])
    decisions = await prescreen_snapshot(snap, use_history=False)
    assert decisions["latency_arbitrage"] is True
    assert decisions["scalping"] is True
    # No swap, no bonus → still skipped.
    assert decisions["swap_arbitrage"] is False
    assert decisions["bonus_abuse"] is False


@pytest.mark.asyncio
async def test_swap_present_passes_swap_arbitrage():
    snap = _snapshot(trades=[_trade(1, swaps=5.0)])
    decisions = await prescreen_snapshot(snap, use_history=False)
    assert decisions["swap_arbitrage"] is True
    assert decisions["latency_arbitrage"] is False


@pytest.mark.asyncio
async def test_bonus_event_passes_bonus_abuse():
    snap = _snapshot(
        bonus=[{"id": 1, "login": 80101, "group": "x", "time": "2026-05-08T00:30:00Z", "profit": 100.0}],
    )
    decisions = await prescreen_snapshot(snap, use_history=False)
    assert decisions["bonus_abuse"] is True


@pytest.mark.asyncio
async def test_two_linked_accounts_passes_bonus_abuse():
    snap = _snapshot(
        linked_accounts=[
            {"login": 80102, "link_reasons": ["same_ip"], "opposing_trade_count": 0},
            {"login": 80103, "link_reasons": ["same_device"], "opposing_trade_count": 0},
        ],
    )
    decisions = await prescreen_snapshot(snap, use_history=False)
    assert decisions["bonus_abuse"] is True


@pytest.mark.asyncio
async def test_prior_high_score_overrides_negative_prescreen(db):
    """A previously-flagged account must always be re-evaluated."""
    from app.models import RiskHistorySummary

    await RiskHistorySummary.create(
        mt5_login=70001,
        risk_key="latency_arbitrage",
        payload={"notes": "previously flagged"},
        run_count=3,
        last_score=80,
        last_level="high",
    )

    snap = _snapshot(mt5_login=70001)  # empty trades
    decisions = await prescreen_snapshot(snap, use_history=True)
    assert decisions["latency_arbitrage"] is True
    # Other risks still skipped — history override is per-(login, risk).
    assert decisions["scalping"] is False
