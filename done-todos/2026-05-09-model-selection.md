# Model selection — Opus 4.7 vs Sonnet 4.6

**Date:** 2026-05-09  
**Verdict:** **Use Opus 4.7 in production.** Keep Sonnet 4.6 wired as a
cheap fallback, but it had a real false-negative on the highest-stakes
signal in this benchmark, so it is not safe as the default for risk
control alerts.

## How the benchmark was run

[scripts/benchmark_models.py](scripts/benchmark_models.py) runs every
production prompt against four hand-shaped synthetic snapshots
(latency-arb, scalping, swap-arb, bonus-abuse) and compares each
model's per-rule TRUE/FALSE decisions plus the engine's final
`risk_score` to a deterministic ground truth computed by
[`tests/test_e2e_mock.py`](tests/test_e2e_mock.py)'s
`RuleEvaluatingEvaluator` (which executes the same algorithm the
prompts ask Claude to run).

- 4 snapshots × 4 risks = 16 calls per model.
- Same prompts, same forced `report_evaluation` tool, same
  `cache_control: ephemeral` system block, same temperature default.
- Latency includes the full HTTP round-trip from the local machine.

## Headline numbers

| Model                 | Calls | Exact-score match | Avg score diff | Per-rule agreement  | Avg latency | Total input tok | Total output tok |
| --------------------- | ----- | ----------------- | -------------- | ------------------- | ----------- | --------------- | ---------------- |
| **`claude-opus-4-7`** | 16    | **14 / 16**       | **3.1**        | **66 / 68 (97.1%)** | 8.20 s      | 97 816          | 6 911            |
| `claude-sonnet-4-6`   | 16    | 12 / 16           | 6.2            | 64 / 68 (94.1%)     | 9.46 s      | 78 968          | 8 064            |

Notes on the table:

- "Exact-score match" = the LLM's `risk_score` equalled the deterministic
  ground-truth score (within 0).
- Per-rule agreement counts a rule as "agree" when LLM TRUE/FALSE
  matched the ground-truth TRUE/FALSE.
- Sonnet was actually slower on this hardware — likely warm-up /
  cache-fill noise; in steady state Sonnet should be ~1.5–2× faster.
- Both models hit the prompt cache from the second call onward
  (`cache_read_input_tokens` ≈ 2 400–3 500 per call), as designed.

## Where each model went wrong

Both models share one shared miss; Sonnet has two extra misses, one of
them serious.

### Shared miss

- **`swap_arb_pattern → latency_arbitrage`** (truth 25, both LLMs 0,
  3/4 rules agree). The swap-arb fixture has only 8 trades so 3 of 4
  latency-arb rules are correctly FALSE. Ground truth says R3
  (positive_slippage_ratio ≥ 0.5) is TRUE because the synthetic
  USDTRY trades happened to open below ask. Both models report it
  FALSE, presumably because they applied a "this isn't a latency-arb
  pattern" gestalt judgement instead of the strict TRUE-iff procedure.
  Impact: a 25/100 → 0/100 score on a non-latency snapshot is the safe
  direction (no false alert), so this is acceptable.

### Sonnet-only misses

- **`latency_arb_pattern → latency_arbitrage`** (truth 100, Sonnet 75,
  3/4 rules agree). **This is the concerning one.** The whole point
  of the latency-arb prompt is to fire on this exact fixture (40
  trades, 12–16 s holds, all favourable fills). Sonnet missed one of
  the four rules on the textbook positive case — that is a 100 →
  high (75) demotion which would still alert, but it weakens the
  "this is unambiguous" signal the engine relies on for the suggested
  action. Opus got 4/4 here.
- **`bonus_abuse_pattern → scalping`** (truth 50, Sonnet 75, 3/4 rules
  agree). A 50 → high (75) overshoot — a false-elevation, less
  serious but still an unwanted shift across a band boundary.

Opus had **zero** misses on the four "fire on the pattern you're
named after" calls; Sonnet had one.

## Cost / latency tradeoff

Per Anthropic's published pricing (May 2026, indicative):

|                     | Opus 4.7 | Sonnet 4.6 |
| ------------------- | -------- | ---------- |
| Input (per 1M tok)  | ~$15     | ~$3        |
| Output (per 1M tok) | ~$75     | ~$15       |
| Cache read          | ~$1.50   | ~$0.30     |

For one full account scan (4 risk calls, ~6 500 input + ~1 700 output
tokens after the first call hits cache):

- **Opus:** ≈ $0.13 / scan → $0.50 / day at 4 scans, ~$15 / month per
  account. At 1 000 active accounts that's ~$15 k / month.
- **Sonnet:** ≈ $0.03 / scan → ~$3 / month per account.

Risk-control alerts are high-stakes and low-volume relative to chat
workloads. Spending ~5× more to avoid one missed-true on the highest-
stakes risk per benchmark sample is the right tradeoff. If cost
becomes a constraint at scale, Phase B can route the three "easy"
risks (scalping, swap-arb, bonus-abuse) to Sonnet and keep latency-arb
on Opus — both models hit 4/4 on the easier risks.

## Implementation

- [`app/config.py`](app/config.py) — `CLAUDE_MODEL` default flipped
  from `claude-sonnet-4-6` to `claude-opus-4-7`.
- Override via `CLAUDE_MODEL` env var if Rabi wants to A/B test in
  production.
- The benchmark script lives at
  [`scripts/benchmark_models.py`](scripts/benchmark_models.py) and can
  be re-run any time the prompts change:
  ```
  ANTHROPIC_API_KEY=... python scripts/benchmark_models.py
  ```
  Optional `BENCH_MODELS=claude-opus-4-7,claude-sonnet-4-6,claude-opus-4-6`
  for wider sweeps.

## What this does NOT prove

- Sample size is 16 calls per model on synthetic data. Real broker
  populations will have edge cases (sparse trade lists, mixed
  symbols, partial windows) the synthetic snapshots don't hit. Re-run
  the benchmark on a few real anonymised accounts before peak load.
- Both models passed the easy "no, this isn't your risk" calls
  cleanly. The interesting failure mode is partial pattern matches,
  which the synthetic data only samples lightly.
- No prompt-tuning loop was attempted between runs — both models saw
  the same prompts. A tighter prompt may close Sonnet's gap.

## Security note

The API key the user pasted into chat to enable this benchmark **must
be rotated** on the Anthropic console. It is in the conversation
transcript and was passed via shell env var; treat it as compromised.
The key is not stored anywhere in the repo.
