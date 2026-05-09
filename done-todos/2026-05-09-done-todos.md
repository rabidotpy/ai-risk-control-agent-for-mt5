# Done-Todos — 2026-05-09

Scope: align the codebase with the full set of fields MT5 can expose
(per the broker Admin Deals view screenshot), tighten the Claude prompts
so the LLM has a precise, deterministic specification of every rule, and
prove the end-to-end pipeline with realistic mock broker data.

## Schema

- [x] Promoted previously optional MT5 fields to required on `Trade`:
      `side` ("buy" | "sell"), `open_time`, `close_time` (aliased from wire
      field `time`), `bid_at_open`, `ask_at_open`, `commission`.
- [x] Made envelope `start_time` / `end_time` required on `AlexResponse`
      (they're the only authoritative source of the analysis window).
- [x] Added `LinkedAccount` model and `linked_accounts: list[LinkedAccount]`
      to `AccountSnapshot` so bonus-abuse R3 / R4 (linked-account count and
      opposing trades) become evaluable.
- [x] Updated `bucket_by_login` to (a) read `start_time`/`end_time` from
      the response and (b) accept an optional `linked_accounts_by_login` map
      the scheduler merges in.
- [x] Resolved the new forward reference between `AlexData` and
      `LinkedAccount` with `model_rebuild()`.

## Prompts

- [x] Rewrote `INPUT_PREAMBLE` in [app/risks/base.py](app/risks/base.py)
      to:
  - Open with a clear ROLE statement.
  - Document every wire field — including the new ones — and explain
    `entry` is informational only.
  - Add a `LINKED ACCOUNT` field section.
  - Add a `DERIVED FACTS` section that defines `holding_seconds`,
    "filled in trader's favour", "held across rollover", and `price_pnl`
    once, so each rule prompt can reference them by name.
  - Add an `EVALUATION DISCIPLINE` section (deterministic, no guessing,
    strict thresholds, 4 sig-figs, insufficient_data convention).
  - Tighten OUTPUT instructions (factual one-sentence reasons, no score
    or level in the summary, exact rule text).
- [x] Rewrote each risk-specific prompt to assume full data is present
      and to give Claude an unambiguous algorithm per rule:
  - [latency_arbitrage.py](app/risks/latency_arbitrage.py) — renamed
    `median_holding_time` to `median_holding_time_seconds`; rewrote R3
    to use the now-available `side`/`bid_at_open`/`ask_at_open`.
  - [scalping.py](app/risks/scalping.py) — renamed R1 to its 6h-scaled
    threshold (`trade_count_6h >= 25`) so it's no longer a hidden
    proportional adjustment in the prompt; renamed R4 to a clearer
    metric name (`repeated_lot_sl_tp_pattern_ratio >= 0.5`).
  - [swap_arbitrage.py](app/risks/swap_arbitrage.py) — defined
    `price_pnl = profit − swaps − commission` once in the preamble and
    referenced it from R3 and R4.
  - [bonus_abuse.py](app/risks/bonus_abuse.py) — replaced the now-noisy
    `bonus_active_within_30_days` with `bonus_received_in_window`
    (matches what the data window actually supplies); rewrote R3 and R4
    to read from the new `linked_accounts` array.

## Engine / API

- [x] Engine, scoring, score → level → action mapping unchanged
      (already correct per PRD §6.4). Reviewed `_count_true_sub_rules` /
      `_build_evidence` / `_metric_name` and confirmed they still parse
      the new rule strings correctly.
- [x] HTTP contract on `/analyse_risk` and `/analyses` unchanged.
- [x] MongoDB persistence (upsert on `(mt5_login, start_time, risk_type)`)
      unchanged.

## Tests / mock data

- [x] Updated `tests/fixtures.py` to construct trades with all the now-
      required fields, plus added four risk-shaped builders:
  - `build_latency_arb_snapshot` — 40 trades, 12-16s holds, all
    favourable fills.
  - `build_scalping_snapshot` — 30 trades, identical (volume, SL, TP)
    triple, ~80% win rate.
  - `build_swap_arb_snapshot` — 8 long-held positions with large
    positive `swaps` and ~zero price PnL.
  - `build_bonus_abuse_snapshot` — bonus event + 35 trades within 24h
    - linked accounts (one with opposing trades) + withdrawal within
      72h. Triggers all 5 bonus-abuse rules.
- [x] Added [tests/test_e2e_mock.py](tests/test_e2e_mock.py) — a new
      end-to-end test that uses a `RuleEvaluatingEvaluator` (a fake LLM
      that actually computes each rule from the snapshot the same way the
      prompt asks Claude to). This proves the prompt → tool → engine →
      score pipeline is correct without spending API calls and gives Alex
      / Rabi a deterministic regression base for future prompt edits.
- [x] Updated `test_evidence_dict_keyed_by_metric_name` and the rule-
      string parametrize block in `test_engine.py` to match the renamed
      rule keys.

## Verification

- [x] `pytest -q` → **79 passed**.
- [x] Manual schema check: parsed Alex's exact wire envelope
      (status / start_time / end_time / data / deposits|withdraws|bonus|
      trades) successfully and round-tripped a trade through
      `bucket_by_login`. `time` → `close_time` alias works.

## Not done (out of scope; tracked for follow-up)

- [ ] Real-time event triggers (PRD §5.2): withdrawal_request,
      abnormal_profit, news_window. Schema supports the trigger types but
      no listener service is implemented.
- [ ] Telegram bot service (PRD §7).
- [ ] Email / CS-follow-up agents (PRD §9).
- [ ] Action executor / risk_actions table (PRD §8 + §11).
- [ ] APScheduler 6-hourly scan loop. Currently scans run via
      `POST /analyse_risk`; the scheduler that calls Alex's GET endpoint
      every 6 hours is not yet wired.
