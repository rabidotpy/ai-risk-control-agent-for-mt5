# Data Requirements Matrix — PRD §6.3 sub-rules vs Alex's documented schema

> The strict mapping of every sub-rule to the data fields it *cannot fire without*. Anything not listed here is not strictly required.
> Reference: PRD section 6.3 ("Rule Examples") in `BestWingGlobal_MT5_AI_Risk_Control_Agent_MVP_PRD_EN copy.md`.
> Reference: Alex's documented response schema (deposits / withdraws / trades / bonus arrays).

## Legend

- **WORKS** — the rule can fire on Alex's documented schema as-is.
- **BLOCKED (broker)** — needs a field Alex must add to his payload. Cannot work around without him.
- **BLOCKED (window)** — needs a longer time window than Alex's per-call data; we can solve internally by aggregating stored pulls.
- **BLOCKED (out of scope)** — needs data we never expect to receive (tick-level quotes, peer averages); rule must be approximated or dropped.

---

## 1. Latency Arbitrage

| PRD §6.3 sub-rule                                           | What's strictly needed                                                                | Status            | Notes |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------- | ----- |
| `trade_count_6h >= 30`                                      | `trades` array, `trade.time`                                                          | **WORKS**         | Already on Alex's wire. |
| `median_holding_time <= 30 seconds`                         | `trade.open_time` **and** `trade.close_time`                                          | **BLOCKED (broker)** | Alex sends one timestamp called `time`. Need both endpoints. |
| `profitable trades within quote spike window >= 60%`        | tick-level quote history per symbol + per-trade open + per-trade close + per-trade profit | **BLOCKED (out of scope)** | Tick history is heavy market data we won't get from this API. Replace with a workable proxy (positive-slippage signal) and document the deviation. |
| `positive_slippage_ratio >= 3x peer average`                | per-trade slippage (or `bid_at_open` + `ask_at_open` + direction) **and** a peer baseline computed across accounts in the same group | **BLOCKED (broker + scope)** | Per-trade slippage requires bid/ask at open + buy/sell side. Peer baseline requires cross-account aggregation we don't currently do. Drop the "3x peer" qualifier; use absolute threshold. |

**Net for latency arbitrage:** 1 of 4 PRD-literal rules is currently live. Three need broker fields plus, for the last two, a meaningful scope decision (drop quote-spike windowing; replace 3x-peer with absolute threshold).

---

## 2. Scalping Violation

| PRD §6.3 sub-rule                                | What's strictly needed                                                          | Status                | Notes |
| ------------------------------------------------ | ------------------------------------------------------------------------------- | --------------------- | ----- |
| `trade_count_24h >= 100`                         | trades over the past 24h (any timestamp field)                                  | **BLOCKED (window)**  | Alex's per-call data is 6h. We solve internally by aggregating across the last four stored 6h pulls. No request to Alex needed. |
| `short_holding_ratio_60s >= 70%`                 | `trade.open_time` **and** `trade.close_time`                                    | **BLOCKED (broker)**  | Same `open_time` ask as Latency R2. |
| `win_rate >= 75%`                                | `trade.profit`                                                                   | **WORKS**             | Already on Alex's wire. |
| `repeated lot size / TP / SL pattern = true`     | `trade.volume`, `trade.stop_loss`, `trade.take_profit`                          | **WORKS**             | All three fields are on Alex's wire. |

**Net for scalping:** 2 of 4 live. R1 unblocks itself once we have ≥4 historical pulls in DB. R2 needs `open_time` from Alex.

---

## 3. Swap Arbitrage

| PRD §6.3 sub-rule                          | What's strictly needed                                                                  | Status                | Notes |
| ------------------------------------------ | --------------------------------------------------------------------------------------- | --------------------- | ----- |
| `swap_profit_ratio_30d >= 60%`             | 30 days of `trades` with `swaps` and `profit`                                           | **BLOCKED (window)**  | Internal DB aggregation across 30 days × 4 daily pulls = 120 stored pulls. No request to Alex needed. |
| `positions repeatedly opened before rollover` | `trade.open_time` + the broker's actual rollover hour                                | **BLOCKED (broker)**  | Need `open_time` + confirmation of rollover hour (UTC midnight is a guess). |
| `positions closed after swap posting`      | `trade.close_time` + swap-posting time                                                  | **BLOCKED (broker)**  | Confirm `time` = close_time. Swap-posting time can be assumed = rollover hour. |
| `price movement PnL is low`                | `trade.profit`, `trade.swaps`, `trade.commission`                                       | **WORKS approximately** | Profit + swaps are on the wire. Commission is missing; assume 0 (commission is a small distortion to a "low PnL" check). |

**Net for swap arbitrage:** 1 fully live, 1 approximately live. Two rules need `open_time`/`close_time` clarification + the broker's rollover hour.

---

## 4. Bonus / Credit Abuse

| PRD §6.3 sub-rule                                              | What's strictly needed                                              | Status                | Notes |
| -------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------- | ----- |
| `bonus_used = true` (within last 30 days)                      | bonus events in last 30 days                                        | **BLOCKED (window)**  | Internal DB aggregation. We see only in-window bonuses today. |
| `high leverage / high frequency trading within 24h`            | `account.leverage` AND trade count in 24h after bonus               | **BLOCKED (broker)**  | Frequency half works (with internal 24h aggregation). Leverage is missing — Alex must supply it (per-account, not per-trade). |
| `linked accounts share IP / device / wallet / IB`              | per-account linkage data: list of related logins + sharing vectors   | **BLOCKED (broker)**  | Entirely absent from Alex's schema. Likely a separate endpoint or per-account property. |
| `opposite trades exist among linked accounts`                  | linked-account list + their recent trades                           | **BLOCKED (broker)**  | Depends on linkage data. |
| `withdrawal requested soon after profit`                       | `withdraws[]`, `trades[].profit`, both with timestamps              | **WORKS**             | All on the wire (within 6h window). |

**Net for bonus abuse:** 1 of 5 fully live. R1 unblocks via DB aggregation; R2 partly via aggregation but needs `leverage`; R3/R4 entirely depend on linkage data.

---

## Cross-cutting summary

### Per-trade fields strictly needed from Alex (the "Desperate Need" list)

| Field             | Unblocks (rule count)                                    | Why we cannot work around                                  |
| ----------------- | -------------------------------------------------------- | ---------------------------------------------------------- |
| `open_time`       | Latency R2, Scalping R2, Swap R2 (4 rules)               | Holding time and rollover-spanning are functions of two timestamps. No proxy exists. |
| Confirm `time` semantic | All time-based rules                                | Without knowing if `time` is open or close, every holding/timing computation is undefined. |
| `bid_at_open`     | Latency R4 (positive slippage)                           | Slippage = fill price − quote at fill. Quote is not in the row. |
| `ask_at_open`     | Latency R4                                                | Same. |
| Trade direction (buy/sell) | Latency R4                                       | "In trader's favour" depends on side: `price < ask` for buys, `price > bid` for sells. |

### Per-account fields strictly needed from Alex

| Field        | Unblocks                                | Notes                                                                |
| ------------ | --------------------------------------- | -------------------------------------------------------------------- |
| `leverage`   | Bonus abuse R2 (the "high leverage" half) | Per account, not per trade. Could be on a separate "accounts" endpoint or attached to each row. |

### Cross-account data strictly needed from Alex

| Data                | Unblocks                                  | Notes                                                          |
| ------------------- | ----------------------------------------- | -------------------------------------------------------------- |
| Linked-account list | Bonus abuse R3 + R4                        | Per-account list of related logins with the sharing vector (ip / device / wallet / ib / kyc). Likely a separate endpoint. |

### Things we deliberately don't ask Alex for

| Item                          | Why                                                                |
| ----------------------------- | ------------------------------------------------------------------ |
| 24h / 30d windows of data     | We aggregate from our own DB across stored 6h pulls. Smaller payloads + idempotent replay. |
| Tick-level quote history      | Massive data; out of scope for an MVP risk-control feed. We replace the "quote spike window" rule with a positive-slippage proxy and document the deviation. |
| Peer-average baselines        | Cross-account computation we'd do internally, not request from Alex. The "3x peer" qualifier becomes an absolute threshold. |
| `commission` per trade        | A small distortion in swap-arb R4; defensible to assume 0 with a documented note. Add later if convenient. |
| News calendar                 | Not used by any of the 4 risks. Reserved for the news-window trigger (PRD §5.2), out of scope for the analysis layer. |

---

## What the prompts honestly say today

The prompts in `app/risks/*.py` reflect this matrix: rules whose data is missing return `insufficient_data` with an explicit reason. The score caps reflect what we can actually evaluate:

| Risk                | Live rules | Max score today |
| ------------------- | ---------- | --------------- |
| Latency arbitrage   | 1 of 4     | 25              |
| Scalping            | 2 of 4 (3 once aggregation lands)     | 50 (75)         |
| Swap arbitrage      | 1 of 4 (3 once aggregation lands)     | 25 (75)         |
| Bonus abuse         | 1 of 5 (3 once aggregation + leverage land) | 20 (60)   |

When Alex provides each missing field, the corresponding rules light up automatically — no code change required.

---

## Action ladder (in order of leverage)

1. **Send Alex the focused-needs message** (separate file). One conversation, three categories of asks: per-trade fields, per-account leverage, cross-account linkage.
2. **Build internal DB aggregation** across stored pulls so the 24h / 30d / 30-day rules can fire from history (no Alex dependency). This is part of Phase B.
3. **Document the deviations from PRD-literal** (quote spike window, 3x peer average) so anyone reading the prompts and PRD side-by-side knows we knowingly substituted simpler signals.
