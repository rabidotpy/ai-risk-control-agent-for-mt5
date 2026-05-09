"""Benchmark Claude Opus 4.7 vs Sonnet 4.6 on our four risk-shaped snapshots.

For each (model, snapshot, risk) combo:
  - Calls AnthropicEvaluator with the production prompt + tool.
  - Compares the LLM's per-rule true/false decisions to the deterministic
    ground truth produced by tests.test_e2e_mock.RuleEvaluatingEvaluator
    (which executes the exact algorithm the prompt asks Claude to run).
  - Records agreement rate, final risk_score match, latency, token usage.

Run:
  ANTHROPIC_API_KEY=sk-... python scripts/benchmark_models.py

The script prints a markdown table at the end and exits 0. It does NOT
write the API key anywhere.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Make the repo importable when run as `python scripts/benchmark_models.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import _build_result, compute_score
from app.llm import AnthropicEvaluator
from app.risks import ALL_RISKS, Risk
from tests.fixtures import (
    build_bonus_abuse_snapshot,
    build_latency_arb_snapshot,
    build_scalping_snapshot,
    build_swap_arb_snapshot,
)
from tests.test_e2e_mock import _DISPATCH as GROUND_TRUTH_DISPATCH


MODELS = [
    # User-stated targets. If Anthropic resolves these aliases differently,
    # override via the BENCH_MODELS env var as a comma-separated list.
    "claude-opus-4-7",
    "claude-sonnet-4-6",
]
if env_models := os.getenv("BENCH_MODELS"):
    MODELS = [m.strip() for m in env_models.split(",") if m.strip()]


SNAPSHOTS = {
    "latency_arb_pattern": build_latency_arb_snapshot(),
    "scalping_pattern": build_scalping_snapshot(),
    "swap_arb_pattern": build_swap_arb_snapshot(),
    "bonus_abuse_pattern": build_bonus_abuse_snapshot(),
}


@dataclass
class CallResult:
    model: str
    snapshot: str
    risk: str
    truth_score: int
    llm_score: int
    score_diff: int
    rules_total: int
    rules_agree: int
    latency_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    error: str | None = None


def ground_truth_score(risk: Risk, snapshot) -> tuple[int, dict[str, bool]]:
    """Score + per-rule TRUE/FALSE map computed deterministically."""
    truth = GROUND_TRUTH_DISPATCH[risk.key](snapshot)
    rule_truth = {ev["rule"]: bool(ev.get("true")) for ev in truth["evaluations"]}
    n_true = sum(1 for v in rule_truth.values() if v)
    score = compute_score(risk.num_sub_rules, n_true)
    return score, rule_truth


def run_one(evaluator: AnthropicEvaluator, model: str, snap_name: str, snapshot, risk: Risk) -> CallResult:
    truth_score, rule_truth = ground_truth_score(risk, snapshot)
    payload_json = snapshot.model_dump_json()

    t0 = time.perf_counter()
    try:
        # We call the lower-level SDK directly so we can capture token usage,
        # then reuse engine._build_result for score parsing.
        from app.risks import REPORT_EVALUATION_TOOL

        resp = evaluator._client.messages.create(  # noqa: SLF001
            model=model,
            max_tokens=evaluator._max_tokens,  # noqa: SLF001
            system=[{"type": "text", "text": risk.system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=[REPORT_EVALUATION_TOOL],
            tool_choice={"type": "tool", "name": "report_evaluation"},
            messages=[{"role": "user", "content": payload_json}],
        )
    except Exception as exc:  # noqa: BLE001
        return CallResult(
            model=model, snapshot=snap_name, risk=risk.key,
            truth_score=truth_score, llm_score=-1, score_diff=999,
            rules_total=risk.num_sub_rules, rules_agree=0,
            latency_s=time.perf_counter() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )
    latency = time.perf_counter() - t0

    tool_input: dict | None = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = dict(block.input)  # type: ignore[arg-type]
            break
    if tool_input is None:
        return CallResult(
            model=model, snapshot=snap_name, risk=risk.key,
            truth_score=truth_score, llm_score=-1, score_diff=999,
            rules_total=risk.num_sub_rules, rules_agree=0, latency_s=latency,
            error="no tool_use block returned",
        )

    result = _build_result(
        risk=risk, tool_input=tool_input,
        mt5_login=snapshot.mt5_login, trigger_type=snapshot.trigger_type,
    )

    # Per-rule agreement
    llm_rule_truth: dict[str, bool] = {}
    for ev in tool_input.get("evaluations", []):
        if isinstance(ev, dict) and isinstance(ev.get("rule"), str):
            llm_rule_truth[ev["rule"]] = bool(ev.get("true"))
    agree = sum(1 for r, v in rule_truth.items() if llm_rule_truth.get(r) == v)

    usage = getattr(resp, "usage", None)
    return CallResult(
        model=model, snapshot=snap_name, risk=risk.key,
        truth_score=truth_score, llm_score=result.risk_score,
        score_diff=abs(result.risk_score - truth_score),
        rules_total=risk.num_sub_rules, rules_agree=agree,
        latency_s=latency,
        input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        cached_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
    )


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    evaluator = AnthropicEvaluator()
    all_results: list[CallResult] = []

    for model in MODELS:
        print(f"\n=== {model} ===", flush=True)
        for snap_name, snapshot in SNAPSHOTS.items():
            for risk in ALL_RISKS:
                r = run_one(evaluator, model, snap_name, snapshot, risk)
                all_results.append(r)
                tag = "OK " if r.error is None and r.score_diff == 0 and r.rules_agree == r.rules_total else "!! "
                print(
                    f"  {tag}{snap_name:>22} | {risk.key:>18} | "
                    f"truth={r.truth_score:3} llm={r.llm_score:3} diff={r.score_diff:3} "
                    f"agree={r.rules_agree}/{r.rules_total} "
                    f"in={r.input_tokens} out={r.output_tokens} cache={r.cached_tokens} "
                    f"{r.latency_s:.2f}s"
                    + (f"  err={r.error}" if r.error else ""),
                    flush=True,
                )

    # ---- Summary ----
    print("\n\n## Summary\n")
    print("| Model | Calls | Score-exact | Avg score diff | Per-rule agreement | Avg latency | Total in tok | Total out tok | Errors |")
    print("|---|---|---|---|---|---|---|---|---|")
    for model in MODELS:
        rows = [r for r in all_results if r.model == model]
        ok = [r for r in rows if r.error is None]
        exact = sum(1 for r in ok if r.score_diff == 0)
        avg_diff = statistics.mean(r.score_diff for r in ok) if ok else float("nan")
        rule_agree = sum(r.rules_agree for r in ok)
        rule_total = sum(r.rules_total for r in ok)
        avg_lat = statistics.mean(r.latency_s for r in ok) if ok else float("nan")
        in_tok = sum(r.input_tokens for r in ok)
        out_tok = sum(r.output_tokens for r in ok)
        errs = sum(1 for r in rows if r.error)
        print(
            f"| `{model}` | {len(rows)} | {exact}/{len(rows)} | {avg_diff:.1f} | "
            f"{rule_agree}/{rule_total} ({100*rule_agree/max(rule_total,1):.1f}%) | "
            f"{avg_lat:.2f}s | {in_tok} | {out_tok} | {errs} |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
