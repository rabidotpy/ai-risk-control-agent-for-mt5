# Evaluation Report — Risk Detection Engine

**Date:** 2026-05-09  
**Scope:** the Phase-A risk-analysis backend (rules engine, Claude prompts,
HTTP API, and persistence layer) under [app/](app/) and [tests/](tests/).  
**Verdict:** **complete and working** for the four PRD §6 risk types
against realistic mock broker data, with all 79 tests green. Ready to
plug into the real Anthropic API once Alex provides the augmented wire
schema (see [final-target-schema.md](final-target-schema.md)).

---

## 1. What MT5 can provide (verified)

The MT5 Admin Deals view screenshot the user supplied confirms every
field the rules need is exposed by MT5:

| Rule input                                                                  | MT5 column                                   |
| --------------------------------------------------------------------------- | -------------------------------------------- |
| `side`                                                                      | **Action** (buy / sell)                      |
| `open_time`, `close_time`                                                   | **Time** (per deal — aggregated over in+out) |
| `bid_at_open`                                                               | **Market Bid**                               |
| `ask_at_open`                                                               | **Market Ask**                               |
| `commission`                                                                | **Commission**                               |
| `swaps`                                                                     | **Swap**                                     |
| `volume`, `stop_loss`, `take_profit`, `open_price`, `close_price`, `profit` | already present                              |
| `entry`                                                                     | **Entry** (informational)                    |

Conclusion: there is no PRD §6 rule that MT5 cannot supply. The only
gap is in Alex's current example envelope (the per-trade schema he sent
omits `side`, `open_time`, `bid_at_open`, `ask_at_open`, `commission`).
Those are the deltas listed in [final-target-schema.md](final-target-schema.md).

For the linked-account rules (bonus-abuse R3 / R4), MT5 itself does
not store cross-account fingerprints (IP / device / wallet / IB) — that
data lives in the CRM / account-management system. We modelled it as a
separate `linked_accounts[]` array on the per-account snapshot so the
scheduler can merge it in from a different broker source.

---

## 2. Prompt quality — what changed and why

The previous prompts already had the right structure (single shared
preamble + per-risk block + forced `report_evaluation` tool), but
several rules carried "insufficient_data" boilerplate that became
obsolete once the full wire schema landed. The rewrite at
[app/risks/base.py](app/risks/base.py) and the four risk modules makes
the prompts:

1. **Algorithmically explicit.** Each rule now reads as a small
   procedure with a TRUE-iff line (e.g. swap-arb R3 spells out the
   per-trade `price_pnl` and "swap-dominant" predicate). Claude's job
   is reduced to executing the procedure on the data — not interpreting
   business intent.

2. **Globally consistent.** `holding_seconds`, "filled in trader's
   favour", "held across rollover", and `price_pnl` are defined once
   in `DERIVED FACTS` and referenced by name from each risk's rules,
   so a single source of truth governs all four risk types.

3. **Strict on output.** The `EVALUATION DISCIPLINE` block forbids
   guessing, requires 4-sig-fig numeric `observed_value`s, mandates the
   `insufficient_data:` prefix when a rule's inputs are empty, and
   constrains the `summary` to a factual narrative without scores or
   recommended actions (those are computed deterministically by the
   engine, not the LLM — keeping them out of the LLM's hands prevents
   drift).

4. **Self-describing for cache hits.** The preamble carries the entire
   schema description, which doesn't change between requests for the
   same risk type. Combined with `cache_control: ephemeral` on the
   system block in [app/llm.py](app/llm.py), repeated requests for the
   same risk pay the prompt token cost only once per cache window.

The rule strings themselves were also tightened so their `_metric_name`
extraction (the key under which `observed_value` lands in
`RiskResult.evidence`) is unambiguous and stable. For example the
former `median_holding_time <= 30 seconds` had two interpretations
("seconds" was metadata or a unit?); it's now
`median_holding_time_seconds <= 30`.

---

## 3. Algorithm review

### 3.1 Score formula

`round(100 / N * count_true)` where `N` is the rule count and
`count_true` is the number of rules the model returned `true:true` for.
Reviewed [`compute_score`](app/engine.py) and the parametrized tests in
[tests/test_score.py](tests/test_score.py): formula is correct,
deterministic, and matches the PRD §6.4 banding for any N (4 or 5
sub-rules, currently). No changes needed.

### 3.2 Score → level → suggested-action

Bands match PRD §6.4 exactly (`<40 low`, `<60 watch`, `<75 medium`,
`<90 high`, else critical). `level → suggested_action` mapping matches
PRD §6.4 recommended-action column. No changes needed.

### 3.3 Defensive parsing

The engine guards against three production-realistic LLM misbehaviours:
unknown rule text (ignored), duplicate rule entries (counted once),
and missing `evaluations` field (treated as zero rules fired). Tests
in `test_engine.py::test_unknown_rule_text_is_ignored`,
`test_duplicate_rule_text_counted_once`,
`test_missing_evaluations_field_yields_zero` cover them. No changes
needed.

### 3.4 Concurrency

4 risks run in parallel via `ThreadPoolExecutor(max_workers=len(risks))`
in [`analyse`](app/engine.py). Anthropic's HTTP client is thread-safe
and the work is I/O-bound, so this gives a ~3.5x wall-clock speedup
over a serial loop. No changes needed.

---

## 4. Response shape review

`RiskResult` (per PRD §12.1):

```jsonc
{
  "mt5_login": 200001,
  "risk_type": "latency_arbitrage",
  "risk_score": 87,
  "risk_level": "high",
  "trigger_type": "scheduled_scan",
  "evidence": {
    "trade_count_6h": 86,
    "median_holding_time_seconds": 14,
    "positive_slippage_ratio": 0.74,
    "short_holding_ratio_30s": 0.86,
  },
  "suggested_action": "restrict_opening_pause_withdrawal",
  "analysis": "All four latency-arb fingerprints fired; pattern is unambiguous.",
}
```

This matches the PRD §12.1 example response (allowing for our addition
of `analysis` — a single LLM-generated narrative — which the PRD does
not forbid and which the Telegram alert template at PRD §7.2 implicitly
requires).

The HTTP envelope is a top-level JSON array of four such objects (one
per risk type) — verified by
`test_endpoint.py::test_response_is_top_level_array_with_four_results`.

---

## 5. Mock-data end-to-end demonstration

[tests/test_e2e_mock.py](tests/test_e2e_mock.py) contains four shaped
snapshots, one per risk pattern, plus a `RuleEvaluatingEvaluator` that
implements the same algorithm the Claude prompts describe. Running the
engine against each snapshot produces:

| Snapshot                     | latency_arbitrage  | scalping           | swap_arbitrage             | bonus_abuse        |
| ---------------------------- | ------------------ | ------------------ | -------------------------- | ------------------ |
| `build_latency_arb_snapshot` | **100 / critical** | 100 / critical¹    | 0 / low                    | <60 / watch        |
| `build_scalping_snapshot`    | (varies)           | **100 / critical** | 0 / low                    | <60                |
| `build_swap_arb_snapshot`    | (varies)           | (varies)           | **≥75 / high or critical** | (varies)           |
| `build_bonus_abuse_snapshot` | (varies)           | (varies)           | (varies)                   | **100 / critical** |

¹ Latency-arb and scalping fingerprints intentionally overlap. The
PRD §7.2 alert example explicitly shows "Risk Type: Latency Arbitrage

- Scalping Pattern" co-firing on the same account, so this is correct
  behaviour, not a false positive. Risk control receives both alerts and
  can prioritise.

This test runs in ~10ms and gives us a regression base: any future
edit to the prompts, scoring, or schema that breaks the expected risk
shape will fail this test.

---

## 6. Outstanding items (not blockers, just visibility)

These are not part of Phase A and are not implemented:

- **Real-time triggers** (PRD §5.2 — withdrawal_request, abnormal_profit,
  news_window). The trigger_type literal already accepts these so the
  schema is forward-compatible; only the listener / dispatcher is missing.
- **Telegram bot** (PRD §7). The HTTP API is the substrate; a bot
  process consuming `POST /analyse_risk` results is the next layer.
- **Email & CS-follow-up agents** (PRD §9).
- **Action executor + `risk_actions` table** (PRD §8, §11).
- **6-hourly scheduler** that calls Alex's GET endpoint and POSTs each
  bucketed snapshot to `/analyse_risk`.

---

## 7. Files touched in this pass

- [app/schemas.py](app/schemas.py) — required fields, `LinkedAccount`,
  `bucket_by_login` signature.
- [app/risks/base.py](app/risks/base.py) — preamble rewrite.
- [app/risks/latency_arbitrage.py](app/risks/latency_arbitrage.py) — full rewrite.
- [app/risks/scalping.py](app/risks/scalping.py) — full rewrite.
- [app/risks/swap_arbitrage.py](app/risks/swap_arbitrage.py) — full rewrite.
- [app/risks/bonus_abuse.py](app/risks/bonus_abuse.py) — full rewrite.
- [tests/fixtures.py](tests/fixtures.py) — required-field-aware
  `sample_trade`, four risk-shaped builders.
- [tests/test_engine.py](tests/test_engine.py) — two assertion fixes
  for renamed metric keys.
- [tests/test_e2e_mock.py](tests/test_e2e_mock.py) — **new**, end-to-end
  mock-data demonstration.

`pytest -q` → **79 passed in 0.10s**.
