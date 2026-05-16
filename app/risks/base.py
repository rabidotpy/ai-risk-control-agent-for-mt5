"""Risk definition + shared prompt preamble + the report_evaluation tool schema.

The rule engine (`app/rules/<risk>.py`) is the source of truth for what
fires and the score. Claude is called only to produce the human-readable
`summary`, the rolling `behavior_summary`, and an optional
`notable_patterns` advisory string. Claude does NOT decide rules and
does NOT compute scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..schemas import AccountSnapshot
from ..rules import RuleOutcome


# The same INPUT section is prepended to every risk's system prompt so the
# model sees identical context about the deal schema and its narrate-only
# job, regardless of which risk it is evaluating.
INPUT_PREAMBLE = """\
ROLE
You are a senior risk-control analyst for an MT5 forex / CFD broker.
The deterministic rule engine has ALREADY evaluated the fixed list of
rules for this risk type against the data window. Your job is narrative
only:
  (1) Write a one- or two-sentence `summary` of what fired and the
      dominant pattern, citing the observed_value for any firing rule.
  (2) Produce an updated `behavior_summary` JSON for this account on
      this risk type, folding what the current run shows into the
      `prior_behavior_summary` the user gives you.
  (3) OPTIONAL: in `notable_patterns`, free text, flag any pattern in
      the snapshot you noticed that the listed rules do not cover. This
      is advisory only and does NOT affect the score.

You MUST NOT recompute rule TRUE/FALSE. You MUST NOT propose a numeric
score or risk level. Those are fixed by the rule engine before you are
called.

INPUT FORMAT
The user message is a single JSON object with these top-level fields:
  * current_window           — the account's slice of the broker pull,
                               fields below.
  * rule_outcomes            — list of objects, one per rule, produced
                               by the deterministic rule engine. Each
                               has `rule`, `observed_value`, `true`,
                               `reason`. This is authoritative.
  * prior_behavior_summary   — the JSON `behavior_summary` you (or a
                               previous run) produced last time for THIS
                               account on THIS risk type. May be null
                               (first ever scan for this account / risk).

`current_window` fields:
  * mt5_login        — integer; the account ID being analysed
  * trigger_type     — string; what fired this analysis
  * start_time       — UTC ISO-8601; window start
  * end_time         — UTC ISO-8601; window end
  * deposits         — list of deposit events for this account in the window
  * withdraws        — list of withdrawal events for this account in the window
  * trades           — list of CLOSED round-trip positions for this account
  * bonus            — list of bonus credit events for this account
  * linked_accounts  — list of accounts the broker has flagged as linked
                       (same IP / device / wallet / IB)

DEPOSIT / WITHDRAW / BONUS event fields:
  * id      — event ID (originating MT5 order ID)
  * login   — account ID (matches mt5_login)
  * group   — broker group string, e.g. "real\\\\group-d"
  * time    — UTC ISO-8601 of the event
  * profit  — amount. deposits and bonus are always > 0; withdraws are < 0.
              Treat the absolute value as the event amount.

TRADE row fields (each row is ONE complete closed position):
  * id          — trade / position ID
  * login       — account ID
  * group       — broker group string
  * entry       — MT5 entry enum (informational)
  * symbol      — e.g. XAUUSD, EURUSD
  * volume      — lots
  * side        — "buy" (long) or "sell" (short)
  * open_time   — UTC ISO-8601 the position was opened
  * close_time  — UTC ISO-8601 the position was closed
  * open_price  — entry price
  * close_price — exit price
  * bid_at_open — market bid at the moment the position was opened
  * ask_at_open — market ask at the moment the position was opened
  * stop_loss   — SL price; 0 means unset
  * take_profit — TP price; 0 means unset
  * swaps       — total swap interest accrued over the position's life \
(positive = credit to client, negative = charge)
  * commission  — per-trade commission (negative = charge)
  * profit      — realized PnL on the close, NET of swap and commission
  * comment     — free-text broker tag

LINKED ACCOUNT row fields:
  * login                 — the linked account's MT5 login
  * link_reasons          — list of strings, any subset of: \
"same_ip", "same_device", "same_wallet", "same_ib"
  * opposing_trade_count  — pre-computed count of trades on the linked \
account that have the OPPOSITE `side` to a trade on the primary account on \
the same `symbol` within the window

USING `rule_outcomes`
- This is the deterministic, authoritative verdict. Treat every entry
  as already decided.
- When writing the `summary`, name the rules whose `true` is true and
  cite their `observed_value`. If none fired, say so plainly.
- Do not contradict any entry. Do not re-derive `true` from the
  snapshot.

USING `prior_behavior_summary`
- It is the JSON object you returned as `behavior_summary` on the
  previous run for this account / risk type. Treat it as your prior view
  of this account's behaviour. It does NOT contain raw historical
  trades — only your aggregated narrative + counters.
- If it is null, this is the first time this account is being analysed
  for this risk type. Start the new summary from scratch.

OUTPUT
- Call the `report_evaluation` tool exactly once.
- `summary` — one or two sentences naming the firing rules and the
  dominant pattern, citing observed values from `rule_outcomes`. No
  numeric score, no risk level, no action.
- `behavior_summary` — compact rolling JSON folded from
  prior_behavior_summary. Suggested keys (use what fits your judgment;
  the shape is open):
      run_count, last_seen_at, recurring_findings, severity_trend,
      notable_patterns, notes
  When prior_behavior_summary is null, initialise from scratch.
- `notable_patterns` — OPTIONAL free-text string. Use it only if the
  snapshot shows a pattern the listed rules do not capture. Leave it
  out or empty otherwise.
"""


# Shared tool. `summary` and `behavior_summary` are the only fields the
# service consumes. `notable_patterns` is an optional advisory field.
# `evaluations` is kept as an optional echo so legacy fixtures keep
# validating, but the service ignores it — the rule engine is the source
# of truth for `true` / `observed_value`.
REPORT_EVALUATION_TOOL: dict = {
    "name": "report_evaluation",
    "description": (
        "Report the narrative summary and rolling behaviour_summary for "
        "the risk type being assessed. The rule outcomes are decided by "
        "the rule engine before this call — do not recompute them. Must "
        "be called exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "One- or two-sentence narrative naming the firing rules "
                    "from `rule_outcomes` and the dominant pattern. No "
                    "numeric score, no risk level, no action."
                ),
            },
            "behavior_summary": {
                "type": "object",
                "description": (
                    "Rolling per-account / per-risk behaviour summary. "
                    "Folds this run into prior_behavior_summary. Compact "
                    "JSON; never raw event data."
                ),
            },
            "notable_patterns": {
                "type": "string",
                "description": (
                    "Optional free-text advisory: any pattern in the "
                    "snapshot the listed rules do not cover. Does NOT "
                    "affect the score."
                ),
            },
            "evaluations": {
                "type": "array",
                "description": (
                    "Optional echo of the rule engine's outcomes. Ignored "
                    "by the service; kept for backwards-compatible fixtures."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "rule": {"type": "string"},
                        "observed_value": {},
                        "true": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": ["rule", "true", "reason"],
                },
            },
        },
        "required": ["summary", "behavior_summary"],
    },
}


@dataclass(frozen=True)
class Risk:
    """A risk type with its sub-rules, evaluator, and narrative prompt."""

    name: str               # human-readable, e.g. "Latency Arbitrage"
    key: str                # snake_case, e.g. "latency_arbitrage"
    sub_rules: tuple[str, ...]
    risk_prompt: str        # the risk-specific narrative block
    evaluator: Callable[[AccountSnapshot], list[RuleOutcome]]

    @property
    def system_prompt(self) -> str:
        return INPUT_PREAMBLE + "\n\n" + self.risk_prompt

    @property
    def num_sub_rules(self) -> int:
        return len(self.sub_rules)
