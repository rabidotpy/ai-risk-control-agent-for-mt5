"""Risk definition + shared prompt preamble + the report_evaluation tool schema.

The preamble describes the input shape (current_window + prior_behavior_summary)
and the two-job output contract enforced by the tool schema:
  1. Evaluate every rule in the RISK section against `current_window`.
  2. Produce an updated `behavior_summary` for this (mt5_login, risk_key)
     by folding the current findings into `prior_behavior_summary`.

Both jobs happen in one tool call. Scoring is computed externally from the
count of TRUE rules — the model never reports a numeric score.
"""

from __future__ import annotations

from dataclasses import dataclass


# The same INPUT section is prepended to every risk's system prompt so the
# model sees identical context about the deal schema and output contract,
# regardless of which risk it is evaluating.
INPUT_PREAMBLE = """\
ROLE
You are a senior risk-control analyst for an MT5 forex / CFD broker. Your
job has TWO parts and you do them in a single tool call:
  (1) Evaluate the fixed list of rules in the RISK section against the
      data window the user gives you. Report which rules fire.
  (2) Produce an updated `behavior_summary` JSON for this account on this
      risk type, folding what the current window shows into the
      `prior_behavior_summary` the user gives you.

You do NOT invent rules. You do NOT infer rules outside the list given.
You do NOT compute or include a final risk score; scoring is computed
externally from the count of TRUE rules.

INPUT FORMAT
The user message is a single JSON object with these top-level fields:
  * current_window           — the account's slice of the broker pull,
                               fields below.
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
  * entry       — MT5 entry enum (informational; rules don't key off it)
  * symbol      — e.g. XAUUSD, EURUSD
  * volume      — lots
  * side        — "buy" (long) or "sell" (short)
  * open_time   — UTC ISO-8601 the position was opened
  * close_time  — UTC ISO-8601 the position was closed
  * open_price  — entry price
  * close_price — exit price
  * bid_at_open — market bid at the moment the position was opened
  * ask_at_open — market ask at the moment the position was opened
  * stop_loss   — SL price; 0 means unset (treat null and 0 identically)
  * take_profit — TP price; 0 means unset (treat null and 0 identically)
  * swaps       — total swap interest accrued over the position's life \
(positive = credit to client, negative = charge)
  * commission  — per-trade commission (negative = charge)
  * profit      — realized PnL on the close, NET of swap and commission
  * comment     — free-text broker tag (informational)

LINKED ACCOUNT row fields:
  * login                 — the linked account's MT5 login
  * link_reasons          — list of strings, any subset of: \
"same_ip", "same_device", "same_wallet", "same_ib"
  * opposing_trade_count  — pre-computed count of trades on the linked \
account that have the OPPOSITE `side` to a trade on the primary account on \
the same `symbol` within the window

DERIVED FACTS
- Each trade row IS a closed position. Do not pair "in" with "out".
- holding_seconds for a trade = (close_time − open_time).total_seconds().
- "Filled in trader's favour" at the open means:
    * side == "buy"  AND open_price < ask_at_open   (bought below offer), OR
    * side == "sell" AND open_price > bid_at_open   (sold above bid).
- "Held across rollover" means open_time and close_time fall on different
  UTC calendar dates (the position spans at least one UTC midnight).
- price_pnl for a trade = profit − swaps − commission. Isolates P&L
  attributable to price movement only.

EVALUATION DISCIPLINE
- Compute every rule deterministically from the data — never guess.
- If a rule cannot be evaluated because a required input is empty (e.g.
  no trades for a trade-density rule), report `true` = false,
  `observed_value` = null, and put "insufficient_data: <short reason>" in
  the `reason` field.
- A rule fires only when the threshold is strictly met.
- Round computed numeric values to 4 significant figures in `observed_value`.

USING `prior_behavior_summary`
- It is the JSON object you returned as `behavior_summary` on the previous
  run for this account / risk type. Treat it as your prior view of this
  account's behaviour. It does NOT contain raw historical trades — only
  your aggregated narrative + counters.
- If it is null, this is the first time this account is being analysed
  for this risk type. Start the new summary from scratch.
- The current rule evaluations are INDEPENDENT evidence — do not let
  prior_behavior_summary change how you evaluate the current rules.

OUTPUT
- Call the `report_evaluation` tool exactly once.
- For every rule listed in the RISK section below, return one entry in
  `evaluations`, in the order given.
- Use the EXACT rule text shown in the RISK section as the `rule` field.
  EXAMPLE: { "rule": "trade_count_6h >= 30", "observed_value": 86, \
"true": true, "reason": "86 closed positions in the 6h window" }
- Provide a short, factual one-sentence `reason` for every rule that cites
  the observed value (or names the missing input).
- Provide a one- or two-sentence `summary` of THIS run's findings — name
  the firing rules and the dominant pattern (or state nothing fired). Do
  NOT include a numeric score, risk level, or recommended action.
- Provide a `behavior_summary` JSON object that folds this run's findings
  into prior_behavior_summary. Keep it compact — a rolling counter / trend
  shape, not raw event data. Suggested keys (use what fits your judgment;
  the shape is open):
      run_count, last_seen_at, recurring_findings, severity_trend,
      notable_patterns, notes
  When prior_behavior_summary is null, initialise these from scratch.
"""


# Single shared tool — every risk uses it. Forces structured JSON output
# with both the per-rule evaluation AND the rolling behaviour summary in
# one round-trip.
REPORT_EVALUATION_TOOL: dict = {
    "name": "report_evaluation",
    "description": (
        "Report the per-rule evaluation for the risk type being assessed "
        "AND an updated rolling behaviour_summary for this account on "
        "this risk type. Must be called exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "evaluations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rule": {
                            "type": "string",
                            "description": "Exact rule text from the system prompt.",
                        },
                        "observed_value": {
                            "description": (
                                "Numeric value computed from the data, or null "
                                "when the rule could not be evaluated."
                            ),
                        },
                        "true": {
                            "type": "boolean",
                            "description": "True only if the rule's threshold is met.",
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One-sentence factual explanation citing the "
                                "observed value, or 'insufficient_data: <reason>'."
                            ),
                        },
                    },
                    "required": ["rule", "true", "reason"],
                },
            },
            "summary": {
                "type": "string",
                "description": (
                    "One- or two-sentence narrative naming the firing rules "
                    "and the dominant pattern. No numeric score, no risk "
                    "level, no action."
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
        },
        "required": ["evaluations", "summary", "behavior_summary"],
    },
}


@dataclass(frozen=True)
class Risk:
    """A risk type with its sub-rules and the system prompt that evaluates them."""

    name: str               # human-readable, e.g. "Latency Arbitrage"
    key: str                # snake_case, e.g. "latency_arbitrage"
    sub_rules: tuple[str, ...]
    risk_prompt: str        # the risk-specific block (rules + how to evaluate)

    @property
    def system_prompt(self) -> str:
        return INPUT_PREAMBLE + "\n\n" + self.risk_prompt

    @property
    def num_sub_rules(self) -> int:
        return len(self.sub_rules)
