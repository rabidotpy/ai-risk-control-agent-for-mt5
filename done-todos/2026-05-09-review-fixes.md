# Review fixes — 2026-05-09

Addresses the 10-point evaluation. Tests: **85 passed in 0.12s**.

## Production-readiness blockers

### 1. Per-risk error containment (engine)

[app/engine.py](app/engine.py) — `analyse()` now wraps each `evaluate_one`
in a try/except so a single Claude failure (network blip, rate limit,
malformed tool response) returns a zero-score `RiskResult` tagged with
`evidence={"error": "<ExcType>: <msg>"}` and `analysis="error: …"`
instead of losing the other three analyses for that account.

- New regression: [tests/test_engine.py](tests/test_engine.py) →
  `test_one_risk_failure_does_not_lose_other_results`.

### 2. Bonus-abuse R2 rescaled for the 6h window

[app/risks/bonus_abuse.py](app/risks/bonus_abuse.py) — renamed
`trades_within_24h_of_bonus >= 30` to
`trades_after_bonus_in_window >= 8` (proportional 30 × 6/24 ≈ 8) and
documented the rationale in the prompt. Will be restored to the literal
24h / 30-trade variant once Phase B aggregation across stored 6h pulls
lands. [tests/test_e2e_mock.py](tests/test_e2e_mock.py) updated.

### 3. Fire-and-forget callback

[app/api.py](app/api.py) — the `/analyse_risk` HTTP response no longer
blocks on `CALLBACK_TIMEOUT_SECONDS`. New `_dispatch_callback` helper:
spawns a daemon thread in production; runs inline only when
`app.config["TESTING"]` is set so the existing assertions on
`callback_capture.calls` remain stable. Callback exceptions are logged,
never raised.

## Polish

### 4. context.md test count

74 → **85** ([context.md](context.md), two locations).

### 5. Stale screenshot notes pruned

[mt5_admin_deals_screenshot_notes.md](.agents/skills/requirement-planner/research/mt5_admin_deals_screenshot_notes.md)
— the "DealReason literal needs expansion + drop dealer" section is now
marked **DEFERRED, not adopted** (no rule keys on `reason`; the broker
schema doesn't carry it; the invented `dealer` value is called out as
invented).

### 6. extra="forbid" on inner row models

[app/schemas.py](app/schemas.py) — `Deposit`, `Withdraw`, `Bonus`,
`Trade`, and `LinkedAccount` now use `ConfigDict(extra="forbid")` so a
typo like `swaps_total` fails validation loudly instead of silently
defaulting to 0 and breaking swap-arb. The outer `AlexResponse` /
`AlexData` envelopes stay `extra="ignore"` for forward-compatibility
with new top-level sections the broker may add.

- New regressions: [tests/test_schemas.py](tests/test_schemas.py) →
  `test_trade_rejects_unknown_field`,
  `test_deposit_rejects_unknown_field`.

### 7. Window-invariant filtering in bucket_by_login

[app/schemas.py](app/schemas.py) — `bucket_by_login()` now drops
deposits / withdraws / bonuses whose `time` and trades whose
`close_time` fall outside `[start_time, end_time]`. Makes the contract
"snapshot.events ⊆ envelope window" hold by construction so a
misaligned pull can't silently break "in window" rules.

- New regression: [tests/test_schemas.py](tests/test_schemas.py) →
  `test_bucket_by_login_drops_events_outside_window`.

### 8. K sign-off on PRD-literal deviations — TODO for Rabi

Latency-arb R3 (`positive_slippage_ratio >= 0.5`) and R4
(`short_holding_ratio_30s >= 0.6`) deviate from PRD §6.3 R3 ("quote
spike window") and R4 ("3x peer average"). The deviation is documented
in [data_requirements_matrix.md](.agents/skills/requirement-planner/research/data_requirements_matrix.md)
and [context.md](context.md), but K hasn't explicitly signed off.
**Action for Rabi:** send K a one-line confirm before the Telegram
alerts go live. Suggested message:

> Quick confirm before alerts go live: for Latency Arbitrage R3/R4 we
> swapped the PRD's "quote spike window" and "3x peer average" tests
> for `positive_slippage_ratio >= 0.5` and `short_holding_ratio_30s >= 0.6`.
> Reason: tick-level quote history and peer baselines are out of MVP
> reach. The replacements catch the same population on the data we
> have. OK to ship as-is, or hold for the originals?

### 9. Trade.entry default

[app/schemas.py](app/schemas.py) — `entry: int = 0`. A payload that
omits the (informational) MT5 entry enum no longer 400s.

- New regression: `test_trade_entry_defaults_to_zero_when_omitted`.

### 10. Dealer reason — n/a in code

The `dealer` reason was never added to `app/schemas.py` (no DealReason
literal, no `Trade.reason` field exists). Already not in production
code; only the stale screenshot-notes mention is pruned (item 5).

## Smaller nits

- `_metric_name()` whitespace brittleness: documented in the function
  docstring (rule strings are authored consistently). Not changed —
  the cost of a regex parse on every result wasn't worth it.
- `Risk.system_prompt` recomputation: `Risk` is `frozen=True` so
  `cached_property` doesn't compose. The string concat is microseconds;
  left as-is per the original "nit" rating.
- No retry/backoff on Claude calls: now mitigated by point 1 — a single
  failure no longer cascades. Real backoff lands in Phase B alongside
  the scheduler.

## Files touched

- [app/engine.py](app/engine.py) — error containment, logger
- [app/api.py](app/api.py) — fire-and-forget callback dispatch
- [app/schemas.py](app/schemas.py) — `extra="forbid"` on rows, default
  `entry`, window-filtering in `bucket_by_login`
- [app/risks/bonus_abuse.py](app/risks/bonus_abuse.py) — R2 rescale
- [tests/test_engine.py](tests/test_engine.py) — error-containment test
- [tests/test_schemas.py](tests/test_schemas.py) — **new**, window /
  forbid / entry-default tests
- [tests/test_e2e_mock.py](tests/test_e2e_mock.py) — bonus R2 rule key
- [context.md](context.md) — test count
- [mt5_admin_deals_screenshot_notes.md](.agents/skills/requirement-planner/research/mt5_admin_deals_screenshot_notes.md)
  — DealReason section deferred
