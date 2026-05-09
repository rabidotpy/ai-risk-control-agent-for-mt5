# Project context

> Handoff document for any AI session picking up this project. Read this once before touching anything. Below the basics, the doc points you to the canonical references for everything.

## What this project is

An internal AI risk control agent for **BestWingGlobal**, an MT5 forex/CFD broker. The system:

1. Pulls broker data (deposits, withdrawals, trades, bonuses) on a schedule, four times a day at 00:00, 06:00, 12:00, 18:00 UTC.
2. Runs four risk detection rule sets per account using Claude as the analyser, with Python computing the scores deterministically.
3. Stores the analysis in MongoDB.
4. POSTs the result back to the broker.

The four risks are **Latency Arbitrage**, **Scalping Violation**, **Swap Arbitrage**, and **Bonus / Credit Abuse**. Each has 4 or 5 sub rules.

The authoritative spec is the PRD at `.agents/skills/requirement-planner/requirement-docs/BestWingGlobal_MT5_AI_Risk_Control_Agent_MVP_PRD_EN copy.md`. When this file disagrees with the PRD, the PRD wins.

## People

- **Rabi**: building this service. Iterates fast and prefers clean slates over drift.
- **Alex**: backend developer at the broker. Owns the data API we will pull from. Has shared a documented schema but has not yet shared the endpoint URL or the missing fields the rules need.
- **K**: the client (BestWingGlobal stakeholder). Owns scope, response shape, and final approvals. His name is K, not Ken.

Memory files at `~/.claude/projects/-Users-rabiulislam-Desktop-Folders-Work-ai-risk-control-agent-for-mt5/memory/` have more on each role and on Rabi's preferences.

## Architecture at a glance

```
Scheduler (4x daily at 00/06/12/18 UTC)         [PHASE B, not built yet]
                ▼
Pull from Alex's data API                       [PHASE B, not built yet]
GET ALEX_DATA_URL with start_time + end_time
                ▼
AlexResponse: { status, data: { deposits, withdraws, trades, bonus } }
                ▼
bucket_by_login() → list[AccountSnapshot]
(one snapshot per account in the pull)
                ▼
engine.analyse(snapshot, evaluator)
For each of 4 risks (in parallel):
  • Build risk-specific system prompt (preamble + risk block)
  • Call Claude with forced report_evaluation tool
  • Parse evaluations[]; count true sub rules
  • Score = round(100 / N * count_true)
  • Map score → risk_level → suggested_action (PRD §6.4)
Returns list[RiskResult] (4 entries per account)
                ▼
db/repo.save_results: replace_one + upsert per row
Re-runs overwrite stored rows (latest wins)
Unique compound index on (mt5_login, start_time, risk_type)
                ▼
POST to ALEX_RESULT_URL                         [PHASE B, not built yet]
```

## Current state (Phase A is DONE, 85/85 tests green)

What lives in code today:

- `app/schemas.py`: typed `Deposit`, `Withdraw`, `Trade`, `Bonus` matching Alex's documented schema. `AlexResponse` envelope. `AccountSnapshot` per account. `bucket_by_login()` helper. Optional missing fields (`open_time`, `bid_at_open`, `ask_at_open`, `commission`) default to `None`.
- `app/risks/base.py`: `INPUT_PREAMBLE` documenting the typed-arrays input. `Risk` dataclass. `REPORT_EVALUATION_TOOL` schema for Claude tool use.
- `app/risks/{latency_arbitrage, scalping, swap_arbitrage, bonus_abuse}.py`: one file per risk with a `SUB_RULES` tuple plus a risk-specific prompt. Rules whose data is missing return `insufficient_data` with a clear reason.
- `app/engine.py`: orchestrates 4 parallel Claude calls. Score formula, banding, suggested action mapping all live here.
- `app/llm.py`: `AnthropicEvaluator` wrapper using Claude Sonnet 4.6 with prompt caching and forced `tool_choice`.
- `app/db/client.py` and `app/db/repo.py`: Mongo collection setup with three indexes (unique compound on `(mt5_login, start_time, risk_type)`, single on `risk_type`, compound on `(mt5_login, start_time)`). `save_results` uses `replace_one(upsert=True)` so re-runs overwrite.
- `app/api.py`: Flask app with `POST /analyse_risk` (manual entry for now), `GET /analyses`, `GET /healthz`. Not yet driven by a scheduler.
- `app/callback.py`: best-effort POST to `CALLBACK_URL`. Will become `ALEX_RESULT_URL` in Phase B.
- `app/config.py`: env loading via `python-dotenv`.
- `tests/`: 74 tests covering engine, repo, endpoint, callback. Fixtures use `mongomock` and a `FakeEvaluator`. No real Claude API or Mongo connection during tests.

### Code conventions

- Pydantic v2 schemas throughout.
- Flask app factory pattern. Do NOT add `app = create_app()` at module level: it triggers a Mongo connection at import time and breaks pytest collection. Run with `flask --app app.api run`.
- Tests inject dependencies via `create_app(evaluator=..., mongo_client=..., callback_fn=...)`.
- No streaming, no websockets, no async loops. The engine is synchronous and uses `ThreadPoolExecutor(max_workers=4)` for the 4 parallel Claude calls.

## What's left

### Phase B: pull layer + scheduler (not built)

1. Add `ALEX_DATA_URL` and `ALEX_RESULT_URL` to `app/config.py` and `.env.example`.
2. Create `app/ingest/alex_client.py`: GETs Alex's data URL, validates the response into `AlexResponse`.
3. Create `app/db/raw_pulls.py`: stores raw pulls keyed by `start_time` so they can be replayed.
4. Create `app/jobs/scheduler.py`: APScheduler firing at 00/06/12/18 UTC. Pulls, buckets, analyses each login, saves, POSTs to the result URL.
5. Modify `app/api.py`: drop `POST /analyse_risk`, add `POST /run_scan` for manual trigger, keep `GET /analyses`.
6. Tests for the ingest layer using mocked HTTP via the `responses` library.

### Phase C: mock data generator (deferred)

7. A script that generates MT5-dashboard-realistic data so the scheduler can be exercised end to end without Alex's URL.

### Internal-only DB aggregation work (folds into Phase B)

The PRD has rules at 24h and 30d windows. Each Alex pull is only 6h. We solve this on our side by aggregating stored 6h pulls. This unblocks `trade_count_24h >= 100` (Scalping R1) and `bonus_active_within_30_days` (Bonus R1) without needing anything new from Alex.

## Data gaps (waiting on Alex)

The four risk prompts already mark blocked sub rules as `insufficient_data` with a clear reason. As soon as Alex adds the missing fields, the rules light up automatically.

Canonical reference: `.agents/skills/requirement-planner/research/data_requirements_matrix.md`.

| Field                          | Where                     | Sub rules unblocked                                                                  |
| ------------------------------ | ------------------------- | ------------------------------------------------------------------------------------ |
| `open_time` per trade          | trade row                 | 5 (median holding, 30s ratio, 60s ratio, rollover spans, trades within 24h of bonus) |
| `bid_at_open` per trade        | trade row                 | 1 (positive slippage)                                                                |
| `ask_at_open` per trade        | trade row                 | 1 (positive slippage)                                                                |
| `side` (buy or sell) per trade | trade row                 | 1 (positive slippage)                                                                |
| linked accounts data           | probably its own endpoint | 2 (linked count, linked with opposing trades)                                        |

Of 17 sub rules total, 7 are alive today on Alex's documented schema, 2 more come alive once we build the DB aggregation in Phase B (no Alex dependency), and 8 need the fields above.

A drafted message to Alex covering these is in conversation history. The message is conversational, uses bullets for the asks, and avoids double dashes.

## Key decisions and why

- **Hybrid engine: rules in Claude, scoring in Python.** Claude evaluates each sub rule (returns true/false plus observed_value via forced tool use). Python computes the score from the count of trues. Rationale: deterministic and auditable scoring, plus the LLM still provides evidence summaries.
- **Re-runs overwrite stored rows.** The cache-hit short-circuit on `POST /analyse_risk` was removed. Spec from Rabi: "if the data is already present in database, it gets overwritten with fresh data."
- **Response shape is locked.** Fields are `mt5_login`, `risk_type` (snake_case), `risk_score`, `risk_level`, `trigger_type`, `evidence` (dict of metric → observed_value), `suggested_action`, `analysis` (LLM narrative). Do NOT rename `analysis` back to `agent_response`. Do NOT add `rule_id` or `rule_name` or `triggered_sub_rule_content`. The shape went through several iterations and is now final.
- **No `request_id` correlation.** `start_time` is unique per scan and doubles as the correlation key.
- **DB aggregation handles long windows.** Rules referencing 24h or 30d are solved internally. We do NOT ask Alex for wider windows.
- **MongoDB, not SQLite.** Per Rabi's preference. Indexes on `(mt5_login, start_time, risk_type)` compound unique, plus `risk_type` single and `(mt5_login, start_time)` compound.
- **Claude Sonnet 4.6 is the LLM.** Configurable via `CLAUDE_MODEL` env var.
- **Bonus abuse keeps 5 sub rules**, not 3. R3 and R4 (linked accounts) return `insufficient_data` rather than being dropped. Score caps at 60 today until linkage data lands. Once Alex provides it, the rules light up automatically.
- **PRD-literal sub rules we deviated from** are documented in the matrix doc. Specifically: Latency R3 became `positive_slippage_ratio >= 0.5` (we replaced "quote spike window") and Latency R4 became `short_holding_ratio_30s >= 0.6` (we replaced "3x peer average"). The deviation was a scope call: tick-level quote history and cross-account peer baselines are out of MVP reach.

## Hard rules from Rabi

These are non-negotiable. They are also captured in memory files.

1. **Never use double dashes.** Not the em dash (`—`) and not the typewriter double hyphen (`--`). Use connecting words like "and", "so", "because", "which", "since", "but". Or split into two sentences. Applies to drafted messages, doc files, chat replies, and code comments. CLI flags (like `--app`) are functional syntax, not punctuation, so they are fine.
2. **Plain English.** Short words. Short sentences. Avoid jargon when a plain word works.
3. **K's name is K, not Ken.** Always.
4. **Iterate quickly.** Rabi pivots scope often. Treat clean slates as real resets and do not carry old artifacts forward.
5. **Need vs want.** When asking Alex for fields, only ask for what we cannot work around. Things we can solve internally (DB aggregation, assumed-zero commission, dropped peer baselines) are not "needs".
6. **Drafted messages should sound conversational.** Bullets are fine for asks but the prose around them should sound like a person talking, not a spec.

## How to run and test

### Tests

```bash
.venv/bin/pytest -q
```

All 85 tests use mongomock and FakeEvaluator. No real API or DB hit.

### The Flask app (Phase A only, scheduler comes in Phase B)

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY. MONGODB_URI defaults to mongodb://localhost:27017
.venv/bin/flask --app app.api run --port 5000
```

### Manually exercise the analysis path

```bash
curl -X POST http://localhost:5000/analyse_risk \
  -H "Content-Type: application/json" \
  -d @path/to/account_snapshot.json
```

`account_snapshot.json` should match the `AccountSnapshot` model in `app/schemas.py`. `tests/fixtures.py:sample_snapshot()` shows a working example.

### Look at stored analyses

```bash
curl "http://localhost:5000/analyses?mt5_login=200001&start_time=2026-05-08T00:00:00Z"
```

## Where to find more

| If you need to know about...                                      | Look in...                                                                                                                         |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Product requirements (PRD)                                        | `.agents/skills/requirement-planner/requirement-docs/BestWingGlobal_MT5_AI_Risk_Control_Agent_MVP_PRD_EN copy.md`                  |
| Per-rule data requirements matrix                                 | `.agents/skills/requirement-planner/research/data_requirements_matrix.md`                                                          |
| MT5 admin screenshot notes (real reason codes, SL/TP conventions) | `.agents/skills/requirement-planner/research/mt5_admin_deals_screenshot_notes.md`                                                  |
| Earlier plan iterations (v2 through v9)                           | `.agents/skills/requirement-planner/updated-plan/`                                                                                 |
| Skill metadata for the requirement planner                        | `.agents/skills/requirement-planner/SKILL.md`                                                                                      |
| Memory files (project context, preferences, integration facts)    | `~/.claude/projects/-Users-rabiulislam-Desktop-Folders-Work-ai-risk-control-agent-for-mt5/memory/` and the `MEMORY.md` index there |
| Risk prompts                                                      | `app/risks/{latency_arbitrage, scalping, swap_arbitrage, bonus_abuse}.py`                                                          |
| Engine logic (scoring, banding, action mapping)                   | `app/engine.py`                                                                                                                    |
| Schema definitions                                                | `app/schemas.py`                                                                                                                   |

## When in doubt

- The PRD is the spec. The matrix is the per-rule data map. The memory files capture Rabi's preferences and durable project facts.
- Phase A is stable. Don't change response shape. Don't reintroduce dropped fields. Don't add a cache-hit short-circuit to `POST /analyse_risk` (re-runs are supposed to overwrite).
- Phase B awaits Alex's endpoint URL plus the missing fields listed above. You can build the scheduler and pull layer with mocks today and wire to the real URL when Alex delivers.
- If a request from Rabi seems to conflict with something here, ask before assuming. He has been clear that small misunderstandings compound, so a quick clarifying question is always welcome.
