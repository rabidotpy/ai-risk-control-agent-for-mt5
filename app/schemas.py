"""Request and response schemas.

Inbound shape mirrors the typed arrays the broker's API returns:
  { status, start_time, end_time, data: { deposits, withdraws, trades, bonus } }

The four arrays are bucketed by `login` into per-account `AccountSnapshot`
objects which the engine consumes one at a time.

The trade row carries everything MT5's Deals view exposes (see screenshot
in done-todos): id, login, group, action (buy/sell), entry enum, symbol,
volume, swaps, commission, market bid/ask at open, open/close prices, SL,
TP, open/close timestamps, and realized profit. Every rule the PRD §6.3
defines is computable from this shape (the only exception — the linked-
account rules in bonus_abuse R3/R4 — read from the optional
`linked_accounts` array on the snapshot).

The response shape from /analyse_risk and the persistence record stay
unchanged: list of `RiskResult` rows, one per (mt5_login, start_time, risk_type).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# Risk-level bands per PRD §6.4.
RiskLevel = Literal["low", "watch", "medium", "high", "critical"]


# What kicked off the analysis. Currently always "scheduled_scan" because we
# only run on the 4-times-daily schedule, but kept open for future event-driven
# triggers (PRD §5.2).
TriggerType = Literal[
    "scheduled_scan",
    "manual_run",
    "withdrawal_request",
    "abnormal_profit",
    "high_frequency",
    "news_window",
    "bonus_check",
]


# ---------------------------------------------------------------------------
# Alex's typed-arrays input
# ---------------------------------------------------------------------------


# Inner row models use extra="forbid" so a typo in a wire field name (e.g.
# `swaps_total` instead of `swaps`) raises a clear ValidationError instead of
# silently defaulting to 0 and breaking downstream rules. The outer envelope
# stays extra="ignore" because the broker may legitimately add new top-level
# sections (e.g. `linked_accounts`) before we model them.
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
    # latency-arb R3 (positive_slippage_ratio).
    bid_at_open: float
    ask_at_open: float

    stop_loss: float = 0.0         # 0 means unset
    take_profit: float = 0.0       # 0 means unset

    swaps: float = 0.0             # cumulative swap on the position
    commission: float = 0.0        # per-trade commission charge (negative = charge)

    profit: float                  # realized PnL on close (net of swap + commission)


class AlexData(BaseModel):
    """The four typed arrays the broker's API returns under `data`."""

    model_config = ConfigDict(extra="ignore")

    deposits: list[Deposit] = Field(default_factory=list)
    withdraws: list[Withdraw] = Field(default_factory=list)
    trades: list[Trade] = Field(default_factory=list)
    # Note the broker's key is the singular `bonus`, not `bonuses`.
    bonus: list[Bonus] = Field(default_factory=list)
    # Optional cross-account linkage for the bonus-abuse rules. Not part of
    # the per-account trade pull; populated from a separate broker source
    # when available (IP / device / wallet / IB linkage).
    linked_accounts: list["LinkedAccount"] = Field(default_factory=list)


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


class AlexResponse(BaseModel):
    """The full envelope returned by the broker's GET endpoint."""

    model_config = ConfigDict(extra="ignore")

    status: bool
    start_time: datetime
    end_time: datetime
    data: AlexData


# ---------------------------------------------------------------------------
# Per-account snapshot (the engine's input)
# ---------------------------------------------------------------------------


class AccountSnapshot(BaseModel):
    """One account's slice of the broker pull, ready for the engine."""

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


def bucket_by_login(
    response: AlexResponse,
    *,
    trigger_type: TriggerType = "scheduled_scan",
    linked_accounts_by_login: dict[int, list[LinkedAccount]] | None = None,
) -> list[AccountSnapshot]:
    """Split the four typed arrays into per-login snapshots.

    `linked_accounts_by_login` is an optional side-channel — the broker's
    linked-accounts feed isn't part of the same envelope, so callers (the
    scheduler) merge it in here.

    Events whose `time` falls outside `[start_time, end_time]` are dropped
    defensively. If Alex's pull is misaligned (e.g. a bonus event leaks in
    from an adjacent window) every "in window" rule would otherwise be
    silently wrong; filtering at the bucket boundary makes the contract
    that snapshot.events ⊆ [start_time, end_time] hold by construction.
    For trades we use `close_time` as the in-window anchor (each trade row
    is one CLOSED position aggregated from MT5's in+out deals).
    """
    by_login: dict[int, AccountSnapshot] = {}
    linked_map = linked_accounts_by_login or {}
    start_t = response.start_time
    end_t = response.end_time

    def _ensure(login: int) -> AccountSnapshot:
        if login not in by_login:
            by_login[login] = AccountSnapshot(
                mt5_login=login,
                trigger_type=trigger_type,
                start_time=start_t,
                end_time=end_t,
                linked_accounts=linked_map.get(login, []),
            )
        return by_login[login]

    for d in response.data.deposits:
        if start_t <= d.time <= end_t:
            _ensure(d.login).deposits.append(d)
    for w in response.data.withdraws:
        if start_t <= w.time <= end_t:
            _ensure(w.login).withdraws.append(w)
    for t in response.data.trades:
        if start_t <= t.close_time <= end_t:
            _ensure(t.login).trades.append(t)
    for b in response.data.bonus:
        if start_t <= b.time <= end_t:
            _ensure(b.login).bonus.append(b)

    return list(by_login.values())


# ---------------------------------------------------------------------------
# Engine output (unchanged response shape)
# ---------------------------------------------------------------------------


class RiskResult(BaseModel):
    """One per risk type. Response shape locked per Rabi's spec."""

    model_config = ConfigDict(extra="ignore")

    mt5_login: int
    risk_type: str
    risk_score: int
    risk_level: RiskLevel
    trigger_type: TriggerType
    evidence: dict[str, Any]
    suggested_action: str
    analysis: str


# Resolve the forward reference now that LinkedAccount is defined.
AlexData.model_rebuild()
