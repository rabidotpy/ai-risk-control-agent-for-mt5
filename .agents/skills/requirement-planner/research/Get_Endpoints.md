# GET Endpoints Required from Alex's Backend

**Project:** BWG MT5 AI Risk Control Agent
**Author:** Rabi
**Date:** 05-05-2026
**Status:** Research draft — building an understanding of what data the agent needs
**Examples used throughout:** `XAUUSD` (Gold) and `BTCUSD` (Bitcoin CFD)

> **Purpose of this document.** This is a research and requirements file, not an API contract. The goal is to develop a clear understanding of:
>
> 1. **Which endpoints** the agent must read from to do its job.
> 2. **What request inputs** each one takes (so we know how the agent will query).
> 3. **What response data** comes back (so we know what the LLM and rule engine will reason over).
> 4. **Why we need each piece of data** — the reasoning that ties every field to a risk-detection signal.
>
> Authentication, rate limiting, error formats, and other transport-layer concerns are deliberately out of scope here. They'll be settled directly with Alex once we agree on _what_ data is needed.

---

## Table of contents

1. [The 13 GET endpoints we need](#1-the-13-get-endpoints-we-need)
2. [Endpoint-by-endpoint research](#2-endpoint-by-endpoint-research)
3. [Data points: what's absolutely required and why](#3-data-points-what-is-absolutely-required-and-why)
4. [How each data point feeds risk detection](#4-how-each-data-point-feeds-risk-detection)
5. [Mapping endpoints to risk types](#5-mapping-endpoints-to-risk-types)

---

## 1. The 13 GET endpoints we need

| #   | Endpoint                     | Purpose                                                     | Used by risk   |
| --- | ---------------------------- | ----------------------------------------------------------- | -------------- |
| 1   | `GET /accounts/{uid}`        | One account snapshot                                        | All            |
| 2   | `GET /accounts/{uid}/groups` | MT5 group config (min hold, leverage, swap rules)           | R2             |
| 3   | `GET /deals`                 | Closed trades (the primary evidence source)                 | R1, R2, R3, R4 |
| 4   | `GET /orders`                | Order requests with request/execution timestamps            | R1             |
| 5   | `GET /positions/{uid}`       | Currently open positions                                    | R3             |
| 6   | `GET /quotes/ticks`          | Historical tick data for a symbol                           | R1             |
| 7   | `GET /symbols/{symbol}`      | Symbol metadata (digits, contract size, swap rates)         | R1, R3         |
| 8   | `GET /withdrawals`           | Withdrawal requests                                         | R4             |
| 9   | `GET /deposits`              | Deposit history                                             | R4             |
| 10  | `GET /bonuses`               | Active and historical bonuses with terms                    | R4             |
| 11  | `GET /logins`                | Login session log (with hashed IPs and device fingerprints) | R3, R4         |
| 12  | `GET /linkage/{uid}`         | Pre-computed linked-account graph                           | R3, R4         |
| 13  | `GET /crm/profile/{uid}`     | CRM categorical profile (no PII)                            | All            |

A 14th `GET /events/feed` is described separately; it's how we'd subscribe to the five PRD event triggers (covered in a sibling doc).

---

## 2. Endpoint-by-endpoint research

Below, each endpoint shows: purpose, request, response, and an example with `XAUUSD` or `BTCUSD`.

---

### 2.1 `GET /accounts/{uid}` — Account snapshot

**Why we need it:** every case starts with the trader's current state. Equity, balance, credit, group membership, and KYC level give the LLM and the rule engine baseline context.

**Request**

```http
GET /v1/accounts/u_8a3f0b2
```

**Response**

```json
{
  "uid": "u_8a3f0b2",
  "login_id": "402198",
  "group": "Pro-Raw-USD",
  "currency": "USD",
  "leverage": 500,
  "balance": 12450.0,
  "equity": 12618.3,
  "credit": 0.0,
  "margin": 880.5,
  "free_margin": 11737.8,
  "margin_level_pct": 1432.78,
  "kyc_level": "tier2",
  "country_code": "SG",
  "registered_at": "2025-11-14T03:21:00.000Z",
  "status": "active",
  "last_activity_at": "2026-05-05T10:21:14.450Z"
}
```

**Why each field matters**

- `group` → tells us the min-hold rule for R2 (Scalping).
- `leverage` → high leverage + sub-minute trades is a latency-arbitrage signature.
- `credit` → flags accounts on bonus (R4).
- `country_code` + `kyc_level` → context only; LLM doesn't act on them.

---

### 2.2 `GET /accounts/{uid}/groups` — MT5 group rules

**Why we need it:** R2 (Scalping Violation) is defined as "broke the group's min-holding-time rule". Without the rule, we can't detect the violation.

**Request**

```http
GET /v1/accounts/u_8a3f0b2/groups
```

**Response**

```json
{
  "group": "Pro-Raw-USD",
  "min_holding_time_seconds": 60,
  "max_leverage": 500,
  "stops_level_points": 0,
  "freeze_level_points": 0,
  "execution_mode": "market",
  "commission_per_lot_usd": 7.0,
  "swap_calculation": "in_points",
  "swap_3_days_on": "wednesday",
  "scalping_allowed": false,
  "hedging_allowed": true,
  "ea_allowed": true
}
```

**Why each field matters**

- `min_holding_time_seconds = 60` and `scalping_allowed = false` → defines R2 threshold for this account.
- `swap_3_days_on` → R3 (Swap Arbitrage) needs this to know which night triple-swap accrues.
- `hedging_allowed` → if true within one account, R3 detection logic shifts to cross-account focus.

---

### 2.3 `GET /deals` — Closed trades

**Why we need it:** the single most important endpoint. Closed deals are the evidence base for all four risks.

**Request**

```http
GET /v1/deals?uid=u_8a3f0b2
              &from=2026-05-04T00:00:00Z
              &to=2026-05-05T00:00:00Z
              &symbol=XAUUSD
              &limit=500
              &cursor=null
```

**Response (XAUUSD example — Gold scalp)**

```json
{
  "data": [
    {
      "deal_id": "998877",
      "uid": "u_8a3f0b2",
      "login_id": "402198",
      "order_id": "778899",
      "position_id": "P-55421",
      "symbol": "XAUUSD",
      "side": "buy",
      "volume": 1.0,
      "open_time": "2026-05-04T10:21:00.250Z",
      "close_time": "2026-05-04T10:21:14.450Z",
      "open_price": 2317.45,
      "close_price": 2319.1,
      "stop_loss": 0,
      "take_profit": 0,
      "profit": 165.0,
      "commission": -7.0,
      "swap": 0.0,
      "net_profit": 158.0,
      "comment": "tp",
      "expert_id": 0
    }
  ],
  "next_cursor": "eyJsYXN0IjoiOTk4ODc3In0="
}
```

**Response (BTCUSD example — held overnight, large notional)**

```json
{
  "data": [
    {
      "deal_id": "1102554",
      "uid": "u_8a3f0b2",
      "login_id": "402198",
      "order_id": "881204",
      "position_id": "P-55502",
      "symbol": "BTCUSD",
      "side": "sell",
      "volume": 0.5,
      "open_time": "2026-05-03T18:30:00.000Z",
      "close_time": "2026-05-04T22:14:51.880Z",
      "open_price": 64020.5,
      "close_price": 63780.0,
      "profit": 120.25,
      "commission": -3.5,
      "swap": 18.4,
      "net_profit": 135.15,
      "comment": "manual close",
      "expert_id": 0
    }
  ],
  "next_cursor": null
}
```

**Why each field matters**

- `open_time` & `close_time` (millisecond) → holding period for R1, R2.
- `position_id` → links related deals (open + close on the same position).
- `expert_id` → if non-zero, an EA placed it. EAs are the typical vehicle for R1.
- `swap` → positive overnight swap on a hedged position is the signature of R3.
- `profit` & `commission` → net profit per second (PnL/holding-time) is a key Layer-1 metric.

---

### 2.4 `GET /orders` — Order request log

**Why we need it:** R1 (Latency Arbitrage) shows up as a small but consistent gap between the trader's request time and the broker's execution time, with the fill price favouring the trader. We need both timestamps.

**Request**

```http
GET /v1/orders?uid=u_8a3f0b2
              &from=2026-05-04T10:00:00Z
              &to=2026-05-04T11:00:00Z
              &symbol=XAUUSD
              &limit=500
```

**Response (XAUUSD — request executed 220 ms later, fill in trader's favour)**

```json
{
  "data": [
    {
      "order_id": "778899",
      "uid": "u_8a3f0b2",
      "symbol": "XAUUSD",
      "side": "buy",
      "type": "market",
      "volume_requested": 1.0,
      "volume_filled": 1.0,
      "request_time": "2026-05-04T10:21:00.030Z",
      "execution_time": "2026-05-04T10:21:00.250Z",
      "request_price": 2317.2,
      "fill_price": 2317.45,
      "slippage_points": 25,
      "slippage_signed_points": 25,
      "deviation_allowed_points": 50,
      "state": "filled",
      "rejection_reason": null,
      "channel": "mt5_terminal",
      "expert_id": 0
    }
  ],
  "next_cursor": null
}
```

**Why each field matters**

- `execution_time - request_time` = **220 ms broker latency**. Under heavy R1 abuse, this gap stays consistently in the trader's favour.
- `slippage_signed_points = 25` (positive = price moved against the trader's request, but trader still profits → suggests they had advance information).
- `channel` → `mt5_terminal` vs `webtrader` vs `mobile` vs `api`. R1 abuse often comes through `api` or third-party terminals.

---

### 2.5 `GET /positions/{uid}` — Open positions

**Why we need it:** R3 (Swap Arbitrage) detection requires _currently open_ hedged positions. Closed deals alone cannot prove an active hedge.

**Request**

```http
GET /v1/positions/u_8a3f0b2
```

**Response**

```json
{
  "data": [
    {
      "position_id": "P-55502",
      "uid": "u_8a3f0b2",
      "login_id": "402198",
      "symbol": "BTCUSD",
      "side": "sell",
      "volume": 0.5,
      "open_time": "2026-05-03T18:30:00.000Z",
      "open_price": 64020.5,
      "current_price": 63915.2,
      "unrealised_pnl": 52.65,
      "swap_accrued": 18.4,
      "stop_loss": 0,
      "take_profit": 0,
      "expert_id": 0
    }
  ],
  "as_of": "2026-05-05T10:30:00.000Z"
}
```

**Why each field matters**

- `swap_accrued` → if a hedged pair across linked accounts both show positive swap_accrued, that's R3 with high confidence.
- `unrealised_pnl ≈ 0` over weeks while `swap_accrued` grows → R3 signature.

---

### 2.6 `GET /quotes/ticks` — Historical tick data

**Why we need it:** R1 (Latency Arbitrage) is fundamentally about _price timing_. We must compare the trader's order against the actual price feed at millisecond resolution.

**Request**

```http
GET /v1/quotes/ticks?symbol=XAUUSD
                    &from=2026-05-04T10:21:00.000Z
                    &to=2026-05-04T10:21:01.000Z
                    &resolution=ms
```

**Response (XAUUSD — 1-second window, sample of ticks)**

```json
{
  "symbol": "XAUUSD",
  "from": "2026-05-04T10:21:00.000Z",
  "to": "2026-05-04T10:21:01.000Z",
  "resolution": "ms",
  "data": [
    { "ts": "2026-05-04T10:21:00.012Z", "bid": 2317.18, "ask": 2317.22 },
    { "ts": "2026-05-04T10:21:00.085Z", "bid": 2317.2, "ask": 2317.24 },
    { "ts": "2026-05-04T10:21:00.150Z", "bid": 2317.22, "ask": 2317.26 },
    { "ts": "2026-05-04T10:21:00.220Z", "bid": 2317.4, "ask": 2317.46 },
    { "ts": "2026-05-04T10:21:00.260Z", "bid": 2317.42, "ask": 2317.48 },
    { "ts": "2026-05-04T10:21:00.500Z", "bid": 2317.45, "ask": 2317.5 }
  ]
}
```

**How we use it (R1 detection example)**
The trader's order was requested at `10:21:00.030Z` at price `2317.20`, but filled at `10:21:00.250Z` at `2317.45`. Between request and fill, the price jumped from 2317.22 → 2317.42 (bid). The trader's request was placed **before** the visible price move, suggesting they had a faster external feed.

**Why this is the hardest endpoint**
Tick data is large. A liquid symbol like BTCUSD can produce tens of thousands of ticks per minute. Alex may need to clarify retention (24h? 7d?) and resolution (ms or 100ms aggregates). Without ticks, R1 becomes much weaker — fall back to deal-level statistics only.

---

### 2.7 `GET /symbols/{symbol}` — Symbol metadata

**Why we need it:** profit calculations and swap interpretations require contract size, tick value, and current swap rates. Without these, the LLM's narrative will be wrong.

**Request**

```http
GET /v1/symbols/XAUUSD
```

**Response (XAUUSD)**

```json
{
  "symbol": "XAUUSD",
  "description": "Gold vs US Dollar",
  "digits": 2,
  "point": 0.01,
  "contract_size": 100,
  "tick_size": 0.01,
  "tick_value_usd": 1.0,
  "currency_base": "XAU",
  "currency_profit": "USD",
  "currency_margin": "USD",
  "swap_long": -3.42,
  "swap_short": 1.15,
  "swap_unit": "points",
  "swap_3_days_on": "wednesday",
  "trade_mode": "full",
  "session_hours_utc": [{ "day": "Mon", "open": "00:00", "close": "23:59" }]
}
```

**Response (BTCUSD)**

```json
{
  "symbol": "BTCUSD",
  "description": "Bitcoin vs US Dollar",
  "digits": 2,
  "point": 0.01,
  "contract_size": 1,
  "tick_size": 0.01,
  "tick_value_usd": 0.01,
  "currency_base": "BTC",
  "currency_profit": "USD",
  "swap_long": -52.1,
  "swap_short": 28.4,
  "swap_unit": "points",
  "swap_3_days_on": "friday",
  "trade_mode": "full",
  "session_hours_utc": "24x7"
}
```

**Why each field matters**

- `swap_short = 28.40` for BTCUSD means a short position _earns_ swap. That makes BTCUSD a favourite vehicle for R3 (open offsetting hedges across linked accounts where the short side collects).
- `swap_3_days_on` → tells the rule engine which night accrues triple swap.
- `contract_size` & `tick_value_usd` → needed for the rule engine to translate "25 points slippage" into "$25 profit per lot".

---

### 2.8 `GET /withdrawals` — Withdrawal requests

**Why we need it:** R4 (Bonus/Credit Abuse) hinges on "deposit → bonus → withdraw quickly".

**Request**

```http
GET /v1/withdrawals?uid=u_8a3f0b2&from=2026-04-01T00:00:00Z&to=2026-05-05T00:00:00Z
```

**Response**

```json
{
  "data": [
    {
      "withdrawal_id": "W-44120",
      "uid": "u_8a3f0b2",
      "amount": 480.0,
      "currency": "USD",
      "method": "bank_transfer",
      "state": "submitted",
      "submitted_at": "2026-05-04T22:14:51.880Z",
      "processed_at": null,
      "rejection_reason": null
    }
  ],
  "next_cursor": null
}
```

**Why each field matters**

- `submitted_at` vs the bonus `granted_at` → time-to-withdrawal is a primary R4 metric.
- `state` — only `submitted` and `pending` can be paused; `completed` cannot.
- No bank account number, no recipient name. The agent never sees them.

---

### 2.9 `GET /deposits` — Deposit history

**Why we need it:** R4 includes "deposit small, claim large bonus, withdraw before turnover". We need the deposit number to compute the deposit-to-bonus ratio.

**Request**

```http
GET /v1/deposits?uid=u_8a3f0b2&from=2026-04-01T00:00:00Z&to=2026-05-05T00:00:00Z
```

**Response**

```json
{
  "data": [
    {
      "deposit_id": "D-77105",
      "uid": "u_8a3f0b2",
      "amount": 10.0,
      "currency": "USD",
      "method": "card",
      "state": "completed",
      "time": "2026-05-04T15:02:11.000Z"
    }
  ],
  "next_cursor": null
}
```

---

### 2.10 `GET /bonuses` — Bonus terms & history

**Why we need it:** without the bonus terms (required turnover, expiry), we cannot know whether a withdrawal is "premature".

**Request**

```http
GET /v1/bonuses?uid=u_8a3f0b2
```

**Response**

```json
{
  "data": [
    {
      "bonus_id": "B-99041",
      "uid": "u_8a3f0b2",
      "type": "deposit_match_5000pct",
      "amount": 500.0,
      "currency": "USD",
      "granted_at": "2026-05-04T15:05:00.000Z",
      "expires_at": "2026-06-04T15:05:00.000Z",
      "required_turnover_lots": 5.0,
      "current_turnover_lots": 0.4,
      "withdraw_lock": true,
      "state": "active"
    }
  ],
  "next_cursor": null
}
```

**Why each field matters**

- `required_turnover_lots` vs `current_turnover_lots` → if turnover ≪ required and a withdrawal is pending, that's R4.
- `withdraw_lock = true` should mean Alex's system already blocks; if a withdrawal still came through, that's a process gap.

---

### 2.11 `GET /logins` — Login session log

**Why we need it:** R3 and R4 both require linkage detection. Same hashed IP and device fingerprint across multiple uids = candidate ring.

**Request**

```http
GET /v1/logins?uid=u_8a3f0b2&from=2026-04-01T00:00:00Z&to=2026-05-05T00:00:00Z
```

**Response**

```json
{
  "data": [
    {
      "session_id": "S-2026-05-04-9921",
      "uid": "u_8a3f0b2",
      "ts": "2026-05-04T15:01:00.000Z",
      "ip_hash": "sha256:b71e...c93",
      "device_fp_hash": "sha256:f04a...210",
      "country_code": "SG",
      "client": "MT5 Terminal",
      "os_family": "Windows"
    }
  ],
  "next_cursor": null
}
```

**Why hashed**
The agent never sees the raw IP. But the _same_ IP across two uids produces the _same_ hash, so we can still match. SHA-256 on a pre-shared salted IP, computed by Alex's backend.

---

### 2.12 `GET /linkage/{uid}` — Pre-computed linked-account graph

**Why we need it:** doing pairwise hash comparisons across thousands of uids is expensive. If Alex's backend already maintains a linkage graph, we just read it.

**Request**

```http
GET /v1/linkage/u_8a3f0b2
```

**Response**

```json
{
  "uid": "u_8a3f0b2",
  "linked": [
    {
      "uid": "u_4d20911",
      "shared": ["ip_hash", "device_fp_hash"],
      "first_seen": "2026-04-12T03:01:00.000Z",
      "confidence": 0.93
    },
    {
      "uid": "u_e90ab73",
      "shared": ["payment_method_hash"],
      "first_seen": "2026-04-22T18:30:00.000Z",
      "confidence": 0.74
    }
  ]
}
```

If Alex doesn't maintain this, we'll compute it ourselves by querying `/logins` periodically and building the graph in our own Postgres. We'd just need IPs and device fingerprints to be consistently hashed with the same salt.

---

### 2.13 `GET /crm/profile/{uid}` — Categorical CRM profile (no PII)

**Why we need it:** the LLM benefits from soft context (segment, language, prior warnings count). Strictly categorical fields and counts; no PII.

**Request**

```http
GET /v1/crm/profile/u_8a3f0b2
```

**Response**

```json
{
  "uid": "u_8a3f0b2",
  "segment": "active_retail",
  "language": "zh",
  "country_code": "SG",
  "kyc_level": "tier2",
  "registered_at": "2025-11-14T03:21:00.000Z",
  "prior_warnings_count": 1,
  "prior_restrictions_count": 0,
  "linked_uids_count": 2,
  "vip_flag": false
}
```

**Why each field matters**

- `language = "zh"` → email draft will be in Chinese.
- `prior_warnings_count = 1` → LLM's score should weight repeat behaviour higher.
- `vip_flag = true` → pre-filter routes the case to a senior officer instead of automated alert.

---

## 3. Data points: what is absolutely required and why

This section is for your understanding, Rabi. Forty-plus fields above can feel overwhelming. Here are the **non-negotiables** — the data points without which a given risk cannot be detected at all.

### 3.1 Time precision (milliseconds, not seconds)

**Required for:** R1 (Latency Arbitrage).

**Why:** R1 hinges on a 100–500 ms gap between order request and execution. Second-precision timestamps make it invisible. If Alex can only provide seconds for ticks or orders, R1 detection drops from ~95% precision to ~40% — basically useless.

### 3.2 Both `request_time` and `execution_time` on every order

**Required for:** R1.

**Why:** the _gap_ between them is the entire signal. Many MT5 APIs only return the execution time. We must have both.

### 3.3 `swap_accrued` per position and `swap` per deal

**Required for:** R3 (Swap Arbitrage).

**Why:** R3 traders hedge for ~zero market PnL but collect overnight swap. The swap value is what they're farming; without it we cannot distinguish a swap arbitrageur from a normal hedger.

### 3.4 Bonus `required_turnover` and `granted_at`

**Required for:** R4 (Bonus/Credit Abuse).

**Why:** "Did the trader meet turnover before withdrawing?" is the core R4 question. Without the requirement number, no answer.

### 3.5 Hashed IP and hashed device fingerprint per session

**Required for:** R3 + R4 (linkage).

**Why:** linked accounts are the strongest signal of organised abuse. Without consistent hashes, we can't link them. Hashes (not raw values) so the agent stays PII-free.

### 3.6 MT5 group's `min_holding_time_seconds`

**Required for:** R2 (Scalping Violation).

**Why:** R2 is by definition "broke the group's min hold rule". The rule must be readable.

### 3.7 `position_id` on every deal

**Required for:** all four risks.

**Why:** lets us join "open" and "close" deals into a position. Without it we can't compute holding time correctly when partial closes occur.

### 3.8 `expert_id` on orders/deals

**Required for:** R1.

**Why:** R1 abuse is almost always done by an EA or external bot, not a manual click. `expert_id != 0` is a fast filter.

### 3.9 Symbol's `swap_long`, `swap_short`, `swap_3_days_on`

**Required for:** R3.

**Why:** the rule engine needs to know which side accrues positive swap and on which night the triple-swap fires.

---

## 4. How each data point feeds risk detection

This is the educational part. Below, each risk has its own table showing **which data points feed which Layer-1 metric**, and what value range triggers the LLM.

### 4.1 R1 — Latency Arbitrage (XAUUSD example)

| Layer-1 metric                | Source data points                                   | Trigger threshold                                         |
| ----------------------------- | ---------------------------------------------------- | --------------------------------------------------------- |
| `pct_deals_under_60s`         | `deals.open_time`, `deals.close_time`                | > 70%                                                     |
| `win_rate_sub_minute`         | `deals.profit`, `deals.close_time - deals.open_time` | > 80%                                                     |
| `avg_broker_latency_ms`       | `orders.execution_time - orders.request_time`        | > 150 ms consistent                                       |
| `pct_fills_in_traders_favour` | `orders.fill_price - orders.request_price`, side     | > 85%                                                     |
| `tick_lead_evidence_count`    | `quotes/ticks` vs `orders.request_time`              | trader requests _before_ a price jump > 5 times in window |
| `expert_id_pct`               | `orders.expert_id != 0`                              | > 90%                                                     |
| `symbol_concentration`        | `deals.symbol`                                       | one symbol > 70% of deal count                            |

**Worked example (XAUUSD):**
Trader's last 24h shows: 218 deals, 82% under 60s, win rate 91%, avg latency 195 ms, 88% fills in trader's favour, expert_id non-zero on all, 78% on XAUUSD. Layer-1 score 87 → escalate to LLM with full evidence pack.

### 4.2 R2 — Scalping Violation (BTCUSD example)

| Layer-1 metric                 | Source data points                         | Trigger threshold |
| ------------------------------ | ------------------------------------------ | ----------------- |
| `min_hold_rule_seconds`        | `accounts/groups.min_holding_time_seconds` | rule from group   |
| `count_deals_under_min_hold`   | `deals` joined with rule                   | > 10 in 24h       |
| `pct_deals_under_min_hold`     | same                                       | > 30%             |
| `total_profit_from_violations` | `deals.profit` filtered                    | > $200            |

**Worked example (BTCUSD):**
Group `Pro-Raw-USD` rule says min hold 60s. Trader has 80 BTCUSD deals in a day; 62 closed in under 30s, totalling +$1,840. Layer-1 score 82 → LLM analysis.

### 4.3 R3 — Swap Arbitrage (BTCUSD example)

| Layer-1 metric                         | Source data points                                                    | Trigger threshold |
| -------------------------------------- | --------------------------------------------------------------------- | ----------------- |
| `linked_uids_with_offsetting_position` | `linkage` + `positions` (opposite sides, same symbol, similar volume) | ≥ 1               |
| `held_across_swap_cutoff_count`        | `positions.open_time` + `symbols.swap_3_days_on`                      | ≥ 3 nights        |
| `swap_to_market_pnl_ratio`             | `positions.swap_accrued / positions.unrealised_pnl`                   | > 5.0             |
| `total_swap_collected_30d`             | `deals.swap` summed                                                   | > $500            |

**Worked example (BTCUSD):**
uid A holds BTCUSD long 0.5 lot, swap_accrued -52. uid B (linked, ip_hash match) holds BTCUSD short 0.5 lot, swap_accrued +28. Combined 30-night swap collected: +$840 with combined market PnL near zero. Layer-1 score 90 → LLM analysis with both accounts in evidence.

### 4.4 R4 — Bonus / Credit Abuse

| Layer-1 metric                     | Source data points                                               | Trigger threshold             |
| ---------------------------------- | ---------------------------------------------------------------- | ----------------------------- |
| `bonus_to_deposit_ratio`           | `bonuses.amount / deposits.amount`                               | > 10                          |
| `pct_turnover_complete`            | `bonuses.current_turnover_lots / bonuses.required_turnover_lots` | < 30% when withdrawal pending |
| `time_to_withdrawal_hours`         | `withdrawals.submitted_at - bonuses.granted_at`                  | < 24h                         |
| `churn_trade_count`                | sub-minute round trips with near-zero net PnL                    | > 50                          |
| `linked_uids_with_same_bonus_type` | `linkage` + `bonuses.type`                                       | ≥ 1                           |

**Worked example:**
Deposit $10 → bonus $500 → 200 churn trades net -$3 over 6 hours → $480 withdrawal request. Layer-1 score 95 → LLM analysis, suggested action: pause withdrawal + assign CS.

---

## 5. Mapping endpoints to risk types

Quick reference — when building the **bundle for one risk**, fetch only what's listed.

| Risk                        | Required endpoints                                                                     | Optional/contextual                      |
| --------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------- |
| **R1 Latency Arbitrage**    | `/accounts/{uid}`, `/deals`, `/orders`, `/quotes/ticks`, `/symbols/{symbol}`           | `/crm/profile`, `/accounts/{uid}/groups` |
| **R2 Scalping Violation**   | `/accounts/{uid}`, `/accounts/{uid}/groups`, `/deals`                                  | `/crm/profile`, `/symbols/{symbol}`      |
| **R3 Swap Arbitrage**       | `/accounts/{uid}`, `/positions/{uid}`, `/deals`, `/symbols/{symbol}`, `/linkage/{uid}` | `/logins`, `/crm/profile`                |
| **R4 Bonus / Credit Abuse** | `/accounts/{uid}`, `/bonuses`, `/deposits`, `/withdrawals`, `/deals`, `/linkage/{uid}` | `/logins`, `/crm/profile`                |

Bundling only the relevant endpoints per risk keeps LLM input small (cost-efficient) and makes the LLM's reasoning more focused (accuracy-efficient).

---

## What this research unblocks

Once we agree on the **set of endpoints** and the **fields each one returns**, the rest falls into place:

- The **rule engine (Layer 1)** can be coded against a known input shape and start producing scores from synthetic data.
- The **LLM evidence bundles** can be templated per risk type without guesswork about which fields are available.
- The **mock adapter** in our dev environment can serve realistic responses, so we can build and test the full pipeline before any real backend integration.
- Conversations with Alex shift from "what could exist?" to "how do we expose what already exists, and what's the smallest delta to fill the gaps?"

In other words: this file is the **shopping list**. Once it's confirmed, we know what we're cooking.
