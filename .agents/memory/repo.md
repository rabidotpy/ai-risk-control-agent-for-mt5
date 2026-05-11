# ai-risk-control-agent-for-mt5 — repo notes

## Stack

- Python 3.13, FastAPI 0.136, uvicorn 0.46, Tortoise ORM 1.1 (asyncpg / aiosqlite), pydantic 2 + pydantic-settings 2, httpx 0.28, anthropic 0.100 (AsyncAnthropic), pytest-asyncio 1.3.
- Venv at `.venv/` — always invoke via `.venv/bin/python` / `.venv/bin/pip` / `.venv/bin/uvicorn` (no `python` on PATH).
- Mongo, Flask, APScheduler, Alex client, raw-pulls cache, mongomock, PyYAML have all been REMOVED.

## Layout

- `app/main.py` — `create_app(evaluator, callback_fn, init_database=True)`. Lifespan does `init_db()`/`close_db()`. Module-level `app = create_app()` for `uvicorn app.main:app`.
- `app/config.py` — `Settings(BaseSettings)` (pydantic-settings, `.env`). Vars: `anthropic_api_key`, `claude_model`, `claude_max_tokens`, `callback_url`, `callback_timeout_seconds`, `database_url` (default `sqlite://:memory:`), `include_history_default` (bool).
- `app/schemas/snapshot.py` — `AccountSnapshot`, `Trade` (alias `time` ↔ `close_time`, `extra=forbid`, `comment: str = ""`), `Deposit`, `Withdraw`, `Bonus`, `LinkedAccount`, `RiskLevel`, `TriggerType`.
- `app/schemas/analysis.py` — `AnalyseRiskRequest`, `BehaviorSummary`, `RiskFinding` (= old `RiskResult` shape + `behavior_summary: dict | None`).
- `app/models/analysis.py` — Tortoise tables: `AnalysisRun` (one row per HTTP call), `RiskEvaluation` (FK→run; indexed on `(mt5_login, risk_key)` and `(mt5_login, window_start)`; append-only audit), `RiskHistorySummary` (`unique_together=(mt5_login, risk_key)`; the rolling per-user-per-risk row).
- `app/db/init.py` — `TORTOISE_ORM` dict; `init_db(generate_schemas=True)` / `close_db()`. **`use_tz=True, timezone="UTC"`** — naive datetimes will warn.
- `app/risks/{base,latency_arbitrage,scalping,swap_arbitrage,bonus_abuse}.py` — `Risk` dataclass + `REPORT_EVALUATION_TOOL` (single tool, `required=[evaluations, summary, behavior_summary]`). **TREND_RULE / `with_trend_rule()` REMOVED.** Sub-rule counts: latency=4, scalping=4, swap=4, bonus=5. Lookback rules replaced with in-window equivalents (e.g. `trade_count_in_window>=25`, `trades_after_bonus_in_window>=8`, `withdrawal_after_bonus_in_window`).
- `app/llm/prompts.py` — `build_user_payload(snapshot, prior_behavior_summary)` returns JSON `{current_window, prior_behavior_summary}`.
- `app/llm/evaluator.py` — `LLMEvaluator` Protocol (async); `AsyncAnthropicEvaluator.evaluate(risk, payload_json)` returns the tool_use input dict. Forced tool use, ephemeral system-prompt cache.
- `app/services/scoring.py` — `compute_score`, `score_to_level`, `level_to_action` (formula unchanged: `round(true/N*100)`; bands 0/40/60/75/90).
- `app/services/callback.py` — async `deliver(body)` via httpx, never raises. Skips when `settings.callback_url` is empty.
- `app/services/analysis.py` — orchestrator. `analyse_snapshots(snapshots, evaluator, include_history, trigger_type) -> (AnalysisRun, [RiskFinding])`. Per-risk: `_load_prior_summary` → `build_user_payload` → `evaluator.evaluate` → `_build_finding` → persist `RiskEvaluation` → `_upsert_summary` (only when `include_history` AND AI returned a summary). Per-risk `async with in_transaction()` so one risk's failure doesn't lose the others; failed risk = zero-score "low" finding with `evidence={"error": "..."}`.
- `app/api/deps.py` — `get_evaluator` / `get_callback` from `app.state` (lazy `AsyncAnthropic` default).
- `app/api/routes.py` — endpoints below. `_coerce_snapshots()` accepts: single dict / list / `{snapshots, include_history}` envelope. ValidationError → 400 with `index` of offender.

## Endpoints

- `GET /healthz` — `{"status":"ok"}`
- `POST /analyse_risk` — body = `AccountSnapshot` | `[AccountSnapshot]` | `{snapshots, include_history}`. Returns flat `[RiskFinding]`. Fires callback once. Persists `AnalysisRun` (with `callback_status`, `finished_at`).
- `GET /analyses?mt5_login=&start_time=ISO` — 404 if empty.
- `GET /history?mt5_login=` — list of `RiskHistorySummary` rows.

## History-aggregation contract (the core feature)

- ONE row per `(mt5_login, risk_key)` in `risk_history_summary`.
- AI is the aggregator: each call's tool output MUST include `behavior_summary` (free-form object). On `include_history=True` the orchestrator overwrites the row with that object verbatim and bumps `run_count`.
- On `include_history=False` the prior summary is NOT loaded into the prompt AND the post-call upsert is skipped.
- The orchestrator NEVER feeds raw historical trades/runs back into the prompt — the only memory the AI sees is its own previous `behavior_summary`.

## Local dev quickstart

```
DATABASE_URL=sqlite://:memory: .venv/bin/uvicorn app.main:app --port 5050
# Open http://127.0.0.1:5050/docs
```

## Tests

- 50 tests, all passing, ~0.2s. `.venv/bin/python -m pytest -q`.
- `pytest.ini`: `asyncio_mode=auto`, `asyncio_default_fixture_loop_scope=function`, DeprecationWarning ignored.
- `tests/conftest.py` exposes: `db` (per-test SQLite-memory Tortoise via `init_db(generate_schemas=True)` then `Tortoise._drop_databases()`), `evaluator` (`FakeEvaluator` with `responses[risk.key]` dict + `calls` log), `callback_fn` (`CapturingCallback`), `app` (FastAPI wired with fakes, `init_database=False`), `client` (`httpx.AsyncClient` over `ASGITransport`). Helpers: `make_snapshot_payload(...)`, `canned_response(sub_rules, true_rules, behavior_summary)`.
- Suite files: `test_schemas.py`, `test_scoring.py`, `test_risks.py`, `test_llm_prompt.py`, `test_analysis_service.py` (history-aggregation flow), `test_routes.py`, `test_callback.py`.

## Trade schema gotchas

- `Trade` uses `populate_by_name=True`; wire field is `time` (alias), serialised name is `close_time`. `model_dump(mode='json')` emits `close_time`.
- `extra="forbid"` on Trade/Deposit/Withdraw/Bonus.
- `Trade.comment: str = ""` accepts broker free-text tags.

## Score arithmetic

- `risk_score = round(true_count / num_sub_rules * 100)`. Levels: <40=low, 40-59=watch, 60-74=medium, 75-89=high, ≥90=critical.

## Common pitfalls hit

- Tortoise with `use_tz=True` emits `RuntimeWarning` for naive datetimes — always use `datetime.now(timezone.utc)`, never `datetime.utcnow()`.
- SQLite-memory + `use_tz=False` caused `/analyses` query 404s because tz-aware request datetimes didn't match naive stored ones. Fixed by `use_tz=True, timezone="UTC"` in TORTOISE_ORM.
- httpx pinning: `httpx==0.30.x` doesn't exist; use `>=0.28`.
- No Aerich migrations yet — `generate_schemas=True` on init. Switch to Aerich before first prod deploy.
- Tortoise 1.x stores connections in a contextvar that is NOT propagated from the FastAPI lifespan task to request tasks. Use `RegisterTortoise(app, config=TORTOISE_ORM, _enable_global_fallback=True)` in lifespan, NOT raw `Tortoise.init()` — otherwise endpoints raise `RuntimeError: No TortoiseContext is currently active`. Tests can still call `init_db()` directly because pytest-asyncio runs them in the same task as the ASGITransport.
- `/analyse_risk` accepts ONLY the envelope `{"snapshots": [...], "include_history": bool|null}` (Pydantic-bound). Bad payloads → FastAPI 422 with `loc: ["body","snapshots",<idx>,"<field>"]`, NOT custom 400.

## Removed (do NOT reintroduce without a design doc)

- Flask, APScheduler, mongomock, pymongo, requests, PyYAML, Alex client, raw-pulls cache, trend rule, lookback rules, scheduled scans.
