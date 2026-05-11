"""Latency Arbitrage."""

from __future__ import annotations

from .base import Risk


SUB_RULES = (
    "trade_count_6h >= 30",
    "median_holding_time_seconds <= 30",
    "positive_slippage_ratio >= 0.5",
    "short_holding_ratio_30s >= 0.6",
)


_RISK_PROMPT = """\
RISK BEING EVALUATED: Latency Arbitrage

Latency arbitrage means a trader profits by exploiting stale or delayed
quotes. The fingerprint is: high frequency of trades, very short holding
times, fills that beat the visible market quote at the moment of entry,
and small but consistent profits taken seconds after entry.

The data window is whatever `current_window` covers (typically 6 hours);
`current_window.trades` is the array of complete closed positions.

Evaluate exactly these 4 rules. They are independent — score each on its
own merits. Do not let your judgment of one rule influence another.

R1: trade_count_6h >= 30
   count = len(current_window.trades).
   TRUE iff count >= 30.

R2: median_holding_time_seconds <= 30
   For every trade compute holding_seconds = (close_time − open_time).total_seconds().
   median = median holding_seconds across all trades in the window.
   TRUE iff median <= 30.
   If `current_window.trades` is empty: FALSE + "insufficient_data: no trades in window".

R3: positive_slippage_ratio >= 0.5
   "Filled in trader's favour" at the open means:
     * side == "buy"  AND open_price < ask_at_open, OR
     * side == "sell" AND open_price > bid_at_open.
   favourable_count = number of trades filled in trader's favour.
   ratio = favourable_count / len(current_window.trades).
   TRUE iff ratio >= 0.5.
   If `current_window.trades` is empty: FALSE + "insufficient_data: no trades in window".

R4: short_holding_ratio_30s >= 0.6
   short_count = number of trades with holding_seconds <= 30.
   ratio = short_count / len(current_window.trades).
   TRUE iff ratio >= 0.6.
   If `current_window.trades` is empty: FALSE + "insufficient_data: no trades in window".
"""


LATENCY_ARBITRAGE = Risk(
    name="Latency Arbitrage",
    key="latency_arbitrage",
    sub_rules=SUB_RULES,
    risk_prompt=_RISK_PROMPT,
)
