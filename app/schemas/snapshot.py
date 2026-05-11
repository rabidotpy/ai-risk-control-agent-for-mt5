"""Per-account snapshot — the sole input shape for /analyse_risk.

One snapshot describes ONE mt5_login's slice of broker data over a window.
The four typed arrays mirror exactly what the broker's MT5 deals view
exposes; every deterministic rule under `app.risks.*` is computable from
this shape alone.

`extra="forbid"` is set on every inner row model so a typo in a wire
field name (e.g. `swaps_total` instead of `swaps`) raises a clear
ValidationError instead of silently defaulting to 0 and breaking
downstream rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Risk-level bands.
RiskLevel = Literal["low", "watch", "medium", "high", "critical"]


# What kicked off the analysis. Open enum so future event-driven triggers
# can be added without a schema bump.
TriggerType = Literal[
    "scheduled_scan",
    "manual_run",
    "withdrawal_request",
    "abnormal_profit",
    "high_frequency",
    "news_window",
    "bonus_check",
]


class Deposit(BaseModel):
    """A deposit event. profit is always > 0 (positive deposit amount)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    login: int
    group: str
    time: datetime
    profit: float


class Withdraw(BaseModel):
    """A withdrawal event. profit is always < 0 (negative amount)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    login: int
    group: str
    time: datetime
    profit: float


class Bonus(BaseModel):
    """A bonus credit event. profit is always > 0."""

    model_config = ConfigDict(extra="forbid")

    id: int
    login: int
    group: str
    time: datetime
    profit: float


class Trade(BaseModel):
    """A complete (closed) round-trip position.

    One row = one closed position aggregated from MT5's "in" + "out" deals.
    Carries everything MT5's Deals view exposes that the rules need:
    direction (`side`), open/close timestamps, market bid/ask at open
    (for slippage detection), per-trade commission, total swap accrued, SL,
    TP, open/close prices, and realized PnL.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int
    login: int
    group: str

    # MT5 entry enum: 0=in, 1=out, 2=inout, 3=out_by. Informational; rules
    # don't currently key off it because each row is already a closed
    # position. Defaults to 0 so a payload that omits it (it's labelled
    # "informational" anyway) still validates.
    entry: int = 0
    symbol: str
    volume: float                  # lots

    # Direction of the position. Required for latency-arb's "filled in
    # trader's favour" check (positive_slippage_ratio).
    side: Literal["buy", "sell"]

    # MT5 deal timestamps. Both are required — every holding-time and
    # rollover rule depends on the pair.
    open_time: datetime
    # The wire field the broker sends today is named `time`; in our internal
    # model we treat it as `close_time`. `populate_by_name=True` (above) lets
    # callers use either name.
    close_time: datetime = Field(alias="time")

    open_price: float
    close_price: float

    # Market quote at the moment the position was opened. Required for
    # latency-arb (positive_slippage_ratio).
    bid_at_open: float
    ask_at_open: float

    stop_loss: float = 0.0         # 0 means unset
    take_profit: float = 0.0       # 0 means unset

    swaps: float = 0.0             # cumulative swap on the position
    commission: float = 0.0        # per-trade commission charge (negative = charge)

    profit: float                  # realized PnL on close (net of swap + commission)

    comment: str = ""              # free-text broker tag (e.g. EA name, signal source); informational


class LinkedAccount(BaseModel):
    """An account flagged as linked to the one being analysed.

    `link_reasons` is the set of attributes that match (any subset of:
    "same_ip", "same_device", "same_wallet", "same_ib"). `opposing_trade_count`
    is the number of trades on the linked account whose direction is opposite
    to a trade on the primary account on the same symbol within the window
    — pre-computed by the broker / a feature service so the LLM doesn't have
    to scan two trade lists.
    """

    model_config = ConfigDict(extra="forbid")

    login: int
    link_reasons: list[str] = Field(default_factory=list)
    opposing_trade_count: int = 0


class AccountSnapshot(BaseModel):
    """One account's slice of broker data — the engine's input."""

    model_config = ConfigDict(extra="ignore")

    mt5_login: int
    trigger_type: TriggerType = "scheduled_scan"
    start_time: datetime
    end_time: datetime
    deposits: list[Deposit] = Field(default_factory=list)
    withdraws: list[Withdraw] = Field(default_factory=list)
    trades: list[Trade] = Field(default_factory=list)
    bonus: list[Bonus] = Field(default_factory=list)
    linked_accounts: list[LinkedAccount] = Field(default_factory=list)
