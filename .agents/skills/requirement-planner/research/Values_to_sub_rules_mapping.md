# Sub-Rules — current state, in plain English

> Last updated: 2026-06-01.
> Documents every sub-rule that is live in the codebase today, what it
> checks, what data it uses, and how the score is computed. The 4 risk
> types from the PRD are joined by a 5th operational risk type
> (Profitable Client Pattern) added on 2026-06-01.

## How the score and the rule engine actually work today

1. **Rules are deterministic Python.** The rule engine in `app/rules/` reads the
   snapshot and produces a list of `RuleOutcome(rule, observed_value, true,
   reason)` per risk type. Same input always produces the same TRUE / FALSE
   pattern. The LLM never decides whether a rule fires.
2. **Score formula.** `round(100 / N × count_true)` where `N` is the number of
   sub-rules. So 3 of 4 fired on a 4-rule risk = 75 (high).
3. **Level bands.** low (0–39), watch (40–59), medium (60–74), high (75–89),
   critical (90+). For a 4-rule risk the possible scores are 0, 25, 50, 75,
   100; medium is unreachable on those.
4. **LLM is called only for narrative.** Summary, behaviour history, and the
   4-item plain-English `evidence_description_list`. It does NOT decide the
   score.
5. **Two threshold gates.** `llm_narrate_min_score = 60` skips the LLM for
   low-scoring findings (templated narrative instead). `callback_min_score = 60`
   skips the Telegram notification for accounts whose max score is below 60.
6. **Prescreen.** A cheap deterministic check (`app/services/prescreen.py`)
   runs before any LLM call and skips obviously-irrelevant risks (e.g. empty
   snapshot, no bonus events for the bonus rule).

---

## 1. Latency Arbitrage (4 sub-rules)

The system looks for traders who exploit a price-feed advantage: very high
frequency, near-100% wins, both buy and sell sides, exits one trade at a time.

### R1 — `trade_count_in_window >= 30`
Has the account placed at least 30 closed positions in the scan window?
A latency-arb playbook requires volume; a normal trader places far fewer.

**Data:** `trades[]` count.
**Status:** LIVE.

### R2 — `median_holding_time_seconds <= 30`
Median of `(close_time - open_time)` across all trades, in seconds.
A real arbitrageur opens and closes in seconds.

**Data:** `open_time`, `close_time`.
**Status:** LIVE. (Was blocked when Alex only sent one timestamp; resolved.)

### R3 — `minority_side_ratio >= 0.2`
`min(buys, sells) / total`. A real arbitrageur trades whichever side the
broker's quote is slow on, so the split tends toward 50/50. A one-directional
trader (e.g. a martingale grid) scores near 0.

**Data:** `side`.
**Status:** LIVE. **Replaced the original PRD `positive_slippage_ratio` rule**
because that rule relied on `bid_at_open`/`ask_at_open` which were defaulted to
zero and caused a false-positive on client account 250030.

### R4 — composite: `win_rate >= 0.9 AND batch_close_ratio <= 0.2`
A real arbitrageur wins almost everything (each entry was near-certain) AND
closes trades one at a time as each opportunity disappears.
`batch_close_ratio` = fraction of trades whose `close_time` second is shared by
3+ other trades. A grid trader closes everything together; the ratio is high.

**Data:** `profit`, `close_time`.
**Status:** LIVE. **Replaced the original PRD `short_holding_ratio_30s` rule**
because that one was redundant with R2 and missed the grid pattern.

---

## 2. Scalping Violation (4 sub-rules)

Very short-duration trades in high frequency, often automated. Whether
scalping is contractually forbidden depends on the account group; this
rule flags the pattern only.

### R1 — `trade_count_in_window >= 25`
At least 25 closed positions in the window. PRD literal was 100 over 24h; we
rescaled to 25 over 6h. Provisional until Phase B 24h aggregation lands.

**Data:** `trades[]` count.
**Status:** LIVE (provisional threshold).

### R2 — `short_holding_ratio_60s >= 0.7`
At least 70% of trades held for 60 seconds or less. The defining trait.

**Data:** `open_time`, `close_time`.
**Status:** LIVE.

### R3 — `win_rate >= 0.75`
At least 75% of trades profitable. Needs at least 5 trades to be meaningful.

**Data:** `profit`.
**Status:** LIVE.

### R4 — `repeated_lot_sl_tp_pattern_ratio >= 0.5`
At least half of trades share a `(volume, stop_loss, take_profit)` triple
with 2 or more other trades. Catches EA bots that fire the same configuration
on every trade. SL and TP of 0 are treated as the same value as null
("unset").

**Data:** `volume`, `stop_loss`, `take_profit`.
**Status:** LIVE.

---

## 3. Swap Arbitrage (4 sub-rules)

The trader profits mostly from overnight swap interest rather than from
price movement. Often holds across UTC midnight, often hedges across linked
accounts to neutralise price risk.

### R1 — `swap_profit_ratio >= 0.6`
`total_swap / total_profit` when total profit is positive. At least 60% of
net profit coming from swap.

**Data:** `swaps`, `profit`.
**Status:** LIVE.

### R2 — `positions_held_across_rollover >= 1`
At least one trade whose `open_time` and `close_time` fall on different
UTC dates. UTC midnight is used as a proxy for the broker's rollover hour.

**Data:** `open_time`, `close_time`.
**Status:** LIVE.

### R3 — `swap_dominant_closed_positions >= 5`
At least 5 trades where positive swap dominates `price_pnl`, defined as
`profit − swaps − commission`, with `abs(price_pnl) <= 0.1 × swaps`.

**Data:** `swaps`, `profit`, `commission`.
**Status:** LIVE.

### R4 — `average_price_movement_pnl_low`
For all positive-swap trades, the ratio of summed `price_pnl` to summed
positive swap falls within `[-0.2, +0.2]`. Meaning price movement is small
relative to swap.

**Data:** `swaps`, `profit`, `commission`.
**Status:** LIVE.

---

## 4. Bonus / Credit Abuse (5 sub-rules, 3 LIVE / 2 DATA-CAPPED)

A trader uses a promotional bonus as margin, often via multiple accounts
that hedge each other so one always wins, then withdraws the winning side.

### R1 — `bonus_received_in_window`
Any bonus event in the snapshot's bonus array.

**Data:** `bonus[]`.
**Status:** LIVE.

### R2 — `trades_after_bonus_in_window >= 8`
At least 8 trades opened at or after the earliest bonus event in the window.
PRD literal was 30 over 24h; rescaled to 8 over 6h. Provisional.

**Data:** `bonus[].time`, `trade.open_time`.
**Status:** LIVE (provisional threshold).

### R3 — `linked_account_count >= 2`
At least 2 accounts linked to this one (shared IP, device, wallet, IB, or KYC).

**Data:** `linked_accounts[]` from CRM.
**Status:** **DATA-CAPPED.** Alex has not delivered the linked-accounts
feed. Until then this rule cannot fire.

### R4 — `linked_with_opposing_trades >= 1`
At least one linked account has a positive `opposing_trade_count`, meaning
it ran trades opposite to this account's trades on the same instrument.

**Data:** `linked_accounts[].opposing_trade_count`.
**Status:** **DATA-CAPPED.** Same dependency as R3.

### R5 — `withdrawal_after_bonus_in_window`
Any withdrawal whose `time` is at or after the earliest bonus event.

**Data:** `bonus[].time`, `withdraws[].time`.
**Status:** LIVE.

---

## 5. Profitable Client Pattern (4 sub-rules) — added 2026-06-01

Not a compliance flag. An operational signal for the dealing desk to decide
whether to route a consistently profitable client to A-book. Strategy-agnostic:
catches discretionary scalpers, trend-followers, news traders, anyone who is
extracting money from the book at a meaningful rate.

### R1 — `profit_extraction_rate >= 100`
`total_profit / window_days >= 100` USD per day. Equivalent to the
$1,000-in-10-days principle the user set, normalised to a daily rate so it
works for any scan window length.

**Data:** `profit` on every trade, snapshot `start_time` and `end_time`.
**Status:** LIVE.

### R2 — composite: `trade_count >= 50 AND profit_factor >= 1.2`
`profit_factor = gross_wins / abs(gross_losses)`. PF = 1.0 is breakeven; PF ≥
1.2 is a real edge. Combined with at least 50 trades, separates skill from
a short lucky streak.

**Data:** `trades[]` count, `profit`.
**Status:** LIVE.

### R3 — `biggest_single_win_share <= 0.30`
The largest single winning trade contributes at most 30% of total gross
wins. Catches the "one lucky trade carries the P&L" case; a real edge
distributes wins across many trades.

**Data:** `profit`.
**Status:** LIVE.

### R4 — `profitable_days_ratio >= 0.60`
At least 60% of distinct trading days in the window ended net positive.
Smooths out one-off lucky days. Requires at least 3 distinct trading days
in the window to be meaningful.

**Data:** `profit`, `close_time`.
**Status:** LIVE.

---

## Quick scoreboard

| Rule | Status | Notes |
| --- | --- | --- |
| Latency: trade_count_in_window >= 30 | LIVE | |
| Latency: median_holding_time <= 30s | LIVE | |
| Latency: minority_side_ratio >= 0.2 | LIVE | Replaced PRD slippage rule |
| Latency: win_rate >= 0.9 AND batch_close_ratio <= 0.2 | LIVE | Replaced PRD short-hold rule |
| Scalping: trade_count_in_window >= 25 | LIVE | Threshold provisional |
| Scalping: short_holding_ratio_60s >= 0.7 | LIVE | |
| Scalping: win_rate >= 0.75 | LIVE | |
| Scalping: repeated_lot_sl_tp_pattern_ratio >= 0.5 | LIVE | |
| Swap: swap_profit_ratio >= 0.6 | LIVE | |
| Swap: positions_held_across_rollover >= 1 | LIVE | |
| Swap: swap_dominant_closed_positions >= 5 | LIVE | |
| Swap: average_price_movement_pnl_low | LIVE | |
| Bonus: bonus_received_in_window | LIVE | |
| Bonus: trades_after_bonus_in_window >= 8 | LIVE | Threshold provisional |
| Bonus: linked_account_count >= 2 | **DATA-CAPPED** | Needs linked-accounts feed |
| Bonus: linked_with_opposing_trades >= 1 | **DATA-CAPPED** | Needs linked-accounts feed |
| Bonus: withdrawal_after_bonus_in_window | LIVE | |
| Profitable: profit_extraction_rate >= 100 | LIVE | |
| Profitable: trade_count >= 50 AND profit_factor >= 1.2 | LIVE | |
| Profitable: biggest_single_win_share <= 0.30 | LIVE | |
| Profitable: profitable_days_ratio >= 0.60 | LIVE | |

**21 sub-rules across 5 risk types. 19 are LIVE. 2 are DATA-CAPPED waiting on Alex's linked-accounts feed.**
