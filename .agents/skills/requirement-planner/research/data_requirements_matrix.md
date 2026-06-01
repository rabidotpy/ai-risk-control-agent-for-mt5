# Data Requirements Matrix — current implementation state

> Last updated: 2026-06-01.
> This file describes what data is actually being used by each live sub-rule
> today, what data is still missing, and what we deliberately chose not to
> request. It replaces the earlier blocker-style matrix; most rules that
> were "BLOCKED" in earlier versions are now live.

## How to read this

Status values used in the per-risk tables below:

- **LIVE** — the rule fires from data we already receive and the code is in production.
- **DATA-CAPPED** — the code is shipped but the rule cannot fire because a required external field is still not delivered. The system returns `insufficient_data` for that rule.
- **DEPRECATED** — the original PRD sub-rule was replaced with a different sub-rule for a documented reason. See the Rule Replacements section.

---

## 1. Latency Arbitrage (4 sub-rules, all LIVE)

| Sub-rule (current) | Data fields it uses | Status |
| --- | --- | --- |
| `trade_count_in_window >= 30` | `trades[]` count | LIVE |
| `median_holding_time_seconds <= 30` | `trade.open_time`, `trade.close_time` | LIVE |
| `minority_side_ratio >= 0.2` | `trade.side` | LIVE |
| `win_rate >= 0.9 AND batch_close_ratio <= 0.2` | `trade.profit`, `trade.close_time` | LIVE |

Two PRD-literal sub-rules were replaced; see Rule Replacements section.

---

## 2. Scalping Violation (4 sub-rules, all LIVE)

| Sub-rule (current) | Data fields it uses | Status |
| --- | --- | --- |
| `trade_count_in_window >= 25` | `trades[]` count | LIVE |
| `short_holding_ratio_60s >= 0.7` | `open_time`, `close_time` | LIVE |
| `win_rate >= 0.75` | `profit` | LIVE |
| `repeated_lot_sl_tp_pattern_ratio >= 0.5` | `volume`, `stop_loss`, `take_profit` | LIVE |

The PRD `trade_count_24h >= 100` threshold was rescaled to `>= 25` for the
6h scan window. Marked provisional until Phase B introduces 24h aggregation
from our own database.

---

## 3. Swap Arbitrage (4 sub-rules, all LIVE)

| Sub-rule (current) | Data fields it uses | Status |
| --- | --- | --- |
| `swap_profit_ratio >= 0.6` | `swaps`, `profit` | LIVE |
| `positions_held_across_rollover >= 1` | `open_time`, `close_time` | LIVE |
| `swap_dominant_closed_positions >= 5` | `swaps`, `profit`, `commission` | LIVE |
| `average_price_movement_pnl_low` | `swaps`, `profit`, `commission` | LIVE |

Open question to Alex: are `commission` and `swaps` truly populated, or
defaulted to zero by his adapter? Currently they are zero on the Islamic
group test account, which may be legitimate (no-swap account) or may hide
a real value. Confirm by next deals export from a non-Islamic account.

---

## 4. Bonus / Credit Abuse (5 sub-rules, 3 LIVE / 2 DATA-CAPPED)

| Sub-rule (current) | Data fields it uses | Status |
| --- | --- | --- |
| `bonus_received_in_window` | `bonus[]` | LIVE |
| `trades_after_bonus_in_window >= 8` | `bonus[].time`, `trade.open_time` | LIVE (provisional threshold) |
| `linked_account_count >= 2` | `linked_accounts[]` | **DATA-CAPPED** |
| `linked_with_opposing_trades >= 1` | `linked_accounts[].opposing_trade_count` | **DATA-CAPPED** |
| `withdrawal_after_bonus_in_window` | `bonus[].time`, `withdraws[].time` | LIVE |

Two sub-rules are blocked because the linked-accounts feed from Alex's
CRM has not been delivered yet. Until that lands, this risk caps at 3 of 5
sub-rules firing, score 60 (medium). The threshold for R2 was rescaled to
`>= 8` for the 6h window (PRD literal was `>= 30` over 24h), provisional
until 24h aggregation is built.

---

## 5. Profitable Client Pattern (4 sub-rules, all LIVE) — NEW

Added 2026-06-01. This is an operational signal for the dealing desk,
not a compliance flag. It identifies consistently profitable clients so
the broker can decide whether to route them to A-book.

| Sub-rule | Data fields it uses | Status |
| --- | --- | --- |
| `profit_extraction_rate >= 100` | `profit`, snapshot `start_time` and `end_time` | LIVE |
| `trade_count >= 50 AND profit_factor >= 1.2` | `trades[]` count, `profit` | LIVE |
| `biggest_single_win_share <= 0.30` | `profit` | LIVE |
| `profitable_days_ratio >= 0.60` | `profit`, `close_time` | LIVE |

Uses only data we already receive. No schema change required.

---

## Rule Replacements (kept for traceability)

| Original PRD sub-rule | What we shipped instead | Reason |
| --- | --- | --- |
| Latency: `positive_slippage_ratio >= 0.5` | `minority_side_ratio >= 0.2` | The slippage rule depended on `bid_at_open` and `ask_at_open` which Alex defaults to zero. Every sell trade then satisfied "open_price > 0" and the rule fired on grids by accident. Caught as a false positive on real client account 250030. |
| Latency: `short_holding_ratio_30s >= 0.6` | `win_rate >= 0.9 AND batch_close_ratio <= 0.2` | The short-hold rule was redundant with R2 (median holding). The replacement captures the cross-trade signal that distinguishes real latency arbitrage (one-by-one exits, near-100% wins) from a martingale grid (batched exits, occasional losses). |
| Latency: `profitable trades in quote spike window >= 60%` | Dropped | Required tick-level quote history which is out of scope. |
| Latency: `positive_slippage_ratio >= 3x peer average` | Dropped (peer averaging) | Cross-account peer baseline computation was not built. Replaced upstream by the slippage rule, then that was also replaced. |
| Scalping: `trade_count_24h >= 100` | `trade_count_in_window >= 25` | Window scaling. Provisional until Phase B 24h aggregation. |
| Bonus: `trades_within_24h_of_bonus >= 30` | `trades_after_bonus_in_window >= 8` | Window scaling. Provisional. |
| Bonus: `withdrawal_within_72h_of_bonus` | `withdrawal_after_bonus_in_window` | The 72h window cannot be checked from a 6h pull. Until Phase B aggregation lands, "after bonus" is the closest honest check. |

---

## Per-trade fields actually used today

| Field on `trade` | Used by | Notes |
| --- | --- | --- |
| `id`, `login`, `group` | All | Identification |
| `symbol` | (no rule keys off it today, but useful in alerts) | Concentration analysis is per-trader, not per-rule |
| `volume` | Scalping R4 | Lot-size bucketing |
| `side` | Latency R3 | Buy / sell direction |
| `open_time`, `close_time` | Latency R2/R4, Scalping R2, Swap R2, Bonus R2 | Both required for any holding-time or rollover rule |
| `open_price`, `close_price` | `derive_exit_reason` (for fallback) | Primary use: classify trade exits |
| `bid_at_open`, `ask_at_open` | **NONE today** | Still required by schema. To be deprecated. |
| `stop_loss`, `take_profit` | Scalping R4, `derive_exit_reason` | |
| `swaps`, `commission` | Swap R1/R3/R4 | |
| `profit` | Many | Net of swap + commission |
| `comment` | `derive_exit_reason` | Brokers tag `[tp ...]` / `[sl ...]` here |

---

## What we still need from Alex

| Item | Unblocks | Why we cannot work around |
| --- | --- | --- |
| Linked-account list | Bonus Abuse R3, R4 | Requires CRM data the MT5 deal stream does not contain. Until delivered, bonus abuse caps at 3 of 5 sub-rules firing. |
| Confirm `commission` and `swaps` are populated | Swap Arbitrage all 4 rules | Currently zero on the Islamic account; need a non-Islamic example to verify the adapter is forwarding the real values. |
| Confirm the `exit_reason` / MT5 deal-reason field would be available IF needed | Future rules | We derive it today from comment + price comparison at 100% accuracy. Worth knowing the field exists in case derivation breaks on another broker. |

---

## What we will not ask for (deliberate)

| Item | Why |
| --- | --- |
| `bid_at_open`, `ask_at_open` | No live rule uses them. Currently defaulted to zero by Alex with no impact. Field should be removed from the schema as cleanup. |
| Tick-level quote history | Out of scope; replaced by simpler proxies. |
| Peer-average baselines | Cross-account computation we would do internally if needed. The PRD "3x peer" qualifier was replaced by absolute thresholds. |
| News calendar | Currently not needed by any live rule. May be useful for a future news-arbitrage rule (PRD §6.3 rule 6 — not yet implemented). |
| 24h / 30d aggregated windows | We will build this from our own database (Phase B) rather than ask Alex to widen the pull. |
