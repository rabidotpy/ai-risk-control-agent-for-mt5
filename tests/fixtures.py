"""Synthetic broker data + canned LLM responses for tests.

`sample_snapshot` is the small generic snapshot used by the engine /
endpoint / repo tests where the LLM is mocked and the data only has to be
structurally valid.

`build_*_snapshot` factories produce richer, semantically meaningful data
(latency-arb pattern, scalping pattern, swap-arb pattern, bonus abuse
pattern). They are used by the analytical end-to-end test that demonstrates
the engine producing the expected risk scores against deterministic mock
broker data without calling the real Claude API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.risks import Risk
from app.schemas import (
    AccountSnapshot,
    Bonus,
    Deposit,
    LinkedAccount,
    Trade,
    Withdraw,
)


WINDOW_START = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc)
# end_time is "start + 6h − 1ms" per Rabi's spec.
WINDOW_END = datetime(2026, 5, 8, 5, 59, 59, 999000, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Generic fixture (used by tests that mock the LLM)
# ---------------------------------------------------------------------------


def sample_trade(
    *,
    trade_id: int,
    minutes_before_end: int = 5,
    holding_seconds: int = 120,
    side: str = "buy",
    profit: float = 0.0,
    swaps: float = 0.0,
    commission: float = 0.0,
    volume: float = 0.10,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    open_price: float = 2300.50,
    close_price: float = 2301.20,
    bid_at_open: float = 2300.45,
    ask_at_open: float = 2300.55,
    symbol: str = "XAUUSD",
) -> Trade:
    close_t = WINDOW_END - timedelta(minutes=minutes_before_end)
    open_t = close_t - timedelta(seconds=holding_seconds)
    return Trade(
        id=trade_id,
        login=200001,
        group="real\\group-d",
        entry=1,  # 1 = out (the closing deal)
        symbol=symbol,
        volume=volume,
        side=side,  # type: ignore[arg-type]
        swaps=swaps,
        commission=commission,
        stop_loss=stop_loss,
        take_profit=take_profit,
        open_price=open_price,
        close_price=close_price,
        bid_at_open=bid_at_open,
        ask_at_open=ask_at_open,
        profit=profit,
        open_time=open_t,
        close_time=close_t,
    )


def sample_snapshot(login: int = 200001) -> AccountSnapshot:
    """A small but structurally complete snapshot the engine can dispatch."""

    trades = [
        sample_trade(trade_id=1001, minutes_before_end=10, profit=3.5),
        sample_trade(trade_id=1002, minutes_before_end=5, profit=-1.2),
    ]
    return AccountSnapshot(
        mt5_login=login,
        trigger_type="scheduled_scan",
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        deposits=[
            Deposit(
                id=897518,
                login=login,
                group="real\\group-d",
                time=WINDOW_START + timedelta(minutes=6),
                profit=200.0,
            )
        ],
        withdraws=[],
        trades=trades,
        bonus=[
            Bonus(
                id=897520,
                login=login,
                group="real\\group-d",
                time=WINDOW_START + timedelta(hours=1),
                profit=100.0,
            )
        ],
        linked_accounts=[],
    )


# ---------------------------------------------------------------------------
# Risk-shaped synthetic snapshots (used by the analytical end-to-end test)
# ---------------------------------------------------------------------------


def build_latency_arb_snapshot(login: int = 300001) -> AccountSnapshot:
    """A textbook latency-arb pattern: ~40 trades, all <30s holds, all filled
    in trader's favour, all small wins on XAUUSD."""

    trades: list[Trade] = []
    for i in range(40):
        # All BUYs, all open below the visible ask (favourable slippage).
        trades.append(
            sample_trade(
                trade_id=10_000 + i,
                minutes_before_end=8 * 60 // 60 - i // 5,  # spread out
                holding_seconds=12 + (i % 5),               # 12-16s holds
                side="buy",
                open_price=2300.40,                         # < ask 2300.55
                close_price=2300.85,
                bid_at_open=2300.45,
                ask_at_open=2300.55,
                profit=4.5,
                volume=0.10,
            )
        )
    return AccountSnapshot(
        mt5_login=login,
        trigger_type="scheduled_scan",
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        trades=trades,
    )


def build_scalping_snapshot(login: int = 300002) -> AccountSnapshot:
    """30 trades, 100% under 60s, ~80% wins, every trade has the same
    (volume, SL, TP) triple."""

    trades: list[Trade] = []
    for i in range(30):
        trades.append(
            sample_trade(
                trade_id=20_000 + i,
                minutes_before_end=10,
                holding_seconds=25 + (i % 10),  # all <= 60s
                side="buy" if i % 2 == 0 else "sell",
                # Identical (volume, SL, TP) for every trade — the bucket rule.
                volume=0.20,
                stop_loss=2295.00,
                take_profit=2305.00,
                open_price=2300.50,
                close_price=2301.10 if i % 5 != 0 else 2300.20,  # ~80% wins
                bid_at_open=2300.45,
                ask_at_open=2300.55,
                profit=2.5 if i % 5 != 0 else -1.5,
            )
        )
    return AccountSnapshot(
        mt5_login=login,
        trigger_type="scheduled_scan",
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        trades=trades,
    )


def build_swap_arb_snapshot(login: int = 300003) -> AccountSnapshot:
    """8 long-held positions across UTC midnight, swap-dominant PnL.

    For the window to contain trades that span UTC midnight, we shift the
    window by one day so it contains both the open (the day before) and the
    close (across midnight). To keep the rest of the suite using
    WINDOW_START unchanged, we use a custom window for this fixture.
    """
    window_start = datetime(2026, 5, 7, 18, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc) - timedelta(milliseconds=1)

    trades: list[Trade] = []
    for i in range(8):
        # Open before midnight UTC, close after — straddles rollover.
        open_t = window_start + timedelta(minutes=10 + i)
        close_t = window_start + timedelta(hours=5, minutes=50 + i)  # well past midnight? actually no
        # Make sure close_t > start_time + 6h - we'll set close just before window_end.
        close_t = window_end - timedelta(minutes=5 - (i % 3))
        trades.append(
            Trade(
                id=30_000 + i,
                login=login,
                group="real\\group-d",
                entry=1,
                symbol="USDTRY",       # high positive carry
                volume=1.0,
                side="buy",
                open_time=open_t,
                close_time=close_t,
                open_price=32.5,
                close_price=32.5 + (0.001 if i % 2 == 0 else -0.001),  # ~zero price PnL
                bid_at_open=32.49,
                ask_at_open=32.51,
                stop_loss=0.0,
                take_profit=0.0,
                swaps=12.0,            # large positive swap
                commission=-0.5,
                # profit is NET of swap+commission; keep price PnL ~0.
                profit=12.0 - 0.5 + (1.0 if i % 2 == 0 else -1.0),
            )
        )
    return AccountSnapshot(
        mt5_login=login,
        trigger_type="scheduled_scan",
        start_time=window_start,
        end_time=window_end,
        trades=trades,
    )


def build_bonus_abuse_snapshot(login: int = 300004) -> AccountSnapshot:
    """Bonus event in window, followed by 35 trades within 24h, two linked
    accounts (one with opposing trades), and a withdrawal within 72h."""

    bonus_time = WINDOW_START + timedelta(minutes=15)
    trades: list[Trade] = []
    for i in range(35):
        open_t = bonus_time + timedelta(minutes=2 + i * 5)
        close_t = open_t + timedelta(seconds=90)
        if close_t > WINDOW_END:
            close_t = WINDOW_END - timedelta(seconds=1)
        trades.append(
            Trade(
                id=40_000 + i,
                login=login,
                group="real\\group-d",
                entry=1,
                symbol="EURUSD",
                volume=0.50,
                side="buy" if i % 2 == 0 else "sell",
                open_time=open_t,
                close_time=close_t,
                open_price=1.0850,
                close_price=1.0855,
                bid_at_open=1.0849,
                ask_at_open=1.0851,
                stop_loss=0.0,
                take_profit=0.0,
                swaps=0.0,
                commission=0.0,
                profit=2.5 if i % 2 == 0 else -1.0,
            )
        )

    return AccountSnapshot(
        mt5_login=login,
        trigger_type="withdrawal_request",
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        bonus=[
            Bonus(
                id=897520,
                login=login,
                group="real\\group-d",
                time=bonus_time,
                profit=500.0,
            )
        ],
        withdraws=[
            Withdraw(
                id=897530,
                login=login,
                group="real\\group-d",
                time=bonus_time + timedelta(hours=20),  # within 72h
                profit=-450.0,
            )
        ],
        trades=trades,
        linked_accounts=[
            LinkedAccount(
                login=200_002,
                link_reasons=["same_ip", "same_device"],
                opposing_trade_count=12,
            ),
            LinkedAccount(
                login=200_003,
                link_reasons=["same_wallet"],
                opposing_trade_count=0,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Canned LLM responses (used when the LLM is mocked)
# ---------------------------------------------------------------------------


def all_true(risk: Risk, summary: str = "all rules fired") -> dict:
    return {
        "evaluations": [
            {"rule": r, "observed_value": 1, "true": True, "reason": "fixture"}
            for r in risk.sub_rules
        ],
        "summary": summary,
    }


def all_false(risk: Risk, summary: str = "no rules fired") -> dict:
    return {
        "evaluations": [
            {"rule": r, "observed_value": 0, "true": False, "reason": "fixture"}
            for r in risk.sub_rules
        ],
        "summary": summary,
    }


def first_n_true(risk: Risk, n: int, summary: str | None = None) -> dict:
    evaluations = []
    for i, rule in enumerate(risk.sub_rules):
        is_true = i < n
        evaluations.append(
            {
                "rule": rule,
                "observed_value": 1 if is_true else 0,
                "true": is_true,
                "reason": "fixture",
            }
        )
    return {
        "evaluations": evaluations,
        "summary": summary or f"{n} of {len(risk.sub_rules)} rules fired",
    }
