# ai-risk-control-agent-for-mt5 — repo notes

## Stack

- Python 3.13, Flask 3, pydantic 2, pymongo 4 + mongomock 4 (tests + dev), APScheduler 3, anthropic 0.100, PyYAML 6.
- Venv at `.venv/` — always invoke via `.venv/bin/python` / `.venv/bin/pip` / `.venv/bin/flask` (no `python` on PATH).

## Layout

- `app/api.py` — Flask `create_app(evaluator, callback_fn, mongo_client, alex_client)`.
- `app/engine.py` — `analyse(snapshot, evaluator, risks=ALL_RISKS, historical_context=None)`. Wraps payload as `{"current_window", "historical_context"}` JSON.
- `app/risks/{latency_arbitrage,scalping,swap_arbitrage,bonus_abuse}.py` — each `Risk` built via `with_trend_rule(...)`. Sub-rule counts: latency=5, scalping=5, swap=5, bonus=6 (last is `prior_high_or_critical_in_last_5_scans >= 3`).
- `app/risks/base.py` — preamble + `TREND_RULE` + `with_trend_rule()`.
- `app/ingest/alex_client.py` — `AlexClient` Protocol, `StubAlexClient` (loads `tests/fixtures/alex_*.json` or `alex_window.json`), `HttpAlexClient`, `get_default_client()` (mode = `ALEX_MODE` env, default `stub`).
- `app/db/client.py` (`risk_analyses` coll) + `app/db/raw_pulls.py` (TTL=35d on `pulled_at`, unique window) + `app/db/repo.py` + `app/db/history.py`.
- `app/history/aggregator.py` — `build_historical_context(...)` returns `{"lookbacks": {...}, "trend_by_risk": {...}}`. Reads `close_time` (serialised) on trades, NOT alias `time`.
- `app/jobs/scan_job.py` — `run_scan(...)` + `latest_completed_window()` (aligns to 00/06/12/18 UTC). `ScanResult` dataclass.
- `app/jobs/scheduler.py` — APScheduler `BackgroundScheduler` cron `0 SCHEDULER_HOURS * * *` UTC. Disabled unless `SCHEDULER_ENABLED=true`. Module entrypoint at `python -m app.jobs.scheduler`.
- `app/openapi.yaml` — hand-written OpenAPI 3.1 spec served at `GET /openapi.yaml`; Swagger UI at `GET /docs` (CDN-loaded).

## Endpoints

- `GET /healthz`, `GET /openapi.yaml`, `GET /docs`
- `POST /analyse_risk` — body = AccountSnapshot, runs all risks synchronously
- `POST /run_scan` — optional `{start_time, end_time}`, defaults to latest completed 6h window. trigger_type=manual_run. 502 on Alex error.
- `GET /analyses?mt5_login=...&start_time=ISO`

## Config (app/config.py)

- `MONGODB_URI` — supports `mongomock://` for in-process mongomock (no docker/mongo needed). Logged with WARNING.
- `MONGODB_DATABASE`, `MONGODB_COLLECTION` (`risk_analyses`), `RAW_PULLS_COLLECTION`, `RAW_PULL_TTL_DAYS=35`.
- `ALEX_MODE` (stub|http), `ALEX_BASE_URL`, `ALEX_API_KEY`, `ALEX_TIMEOUT_SECONDS`, `ALEX_STUB_FIXTURES_DIR=tests/fixtures`.
- `SCHEDULER_ENABLED` (default false), `SCHEDULER_HOURS=0,6,12,18`.

## Local dev quickstart

```
MONGODB_URI=mongomock:// .venv/bin/flask --app app.api run --port 5050
# Open http://127.0.0.1:5050/docs
./tests/fixtures/snapshots/post_all.sh
```

- DO NOT pipe `flask run` through `head` — pipe closing kills the server. Run unpiped.

## Tests

- 108 tests, all passing. `python -m pytest -q` (use `.venv/bin/python -m pytest`).
- `tests/conftest.py` exposes: `FakeEvaluator` (canned responses by risk.key), `CapturingCallback`, `mongo` (mongomock), `collection`, `client` (Flask test client). `client` does NOT pass `alex_client`; create custom fixture for /run_scan tests.
- Snapshot fixtures at `tests/fixtures/snapshots/{clean_account,latency_arbitrage,scalping,swap_arbitrage,bonus_abuse}.json` + `post_all.sh` helper.

## Trade schema gotchas

- `Trade` uses `populate_by_name=True`; wire field is `time` (alias), serialised name is `close_time`. `model_dump(mode='json')` emits `close_time`; aggregator must read `close_time`.
- `extra="forbid"` on Trade/Deposit/Withdraw/Bonus — no unknown fields allowed.
- mongomock strips tzinfo on stored datetimes — tests must `.replace(tzinfo=timezone.utc)` before comparing to original tz-aware datetimes.

## Score arithmetic

- `risk_score = round(true_count / num_sub_rules * 100)`. Levels: 0=none, 1-25=watch, 26-50=medium, 51-75=high, 76-100=critical.
- Adding TREND_RULE bumped denominators (4→5 for 3 risks, 5→6 for bonus). Anyone editing tests must update score expectations.

## Common pitfalls hit

- `replace_string_in_file` with prefix-only `oldString` left old body intact in test_e2e_mock.py → had to truncate with awk. Always include enough trailing context to encompass the full region.
- Flask boot fails fast if pymongo can't reach Mongo; use `MONGODB_URI=mongomock://` for UI exploration.
- No docker installed locally; MongoDB options are mongomock URI or `brew install mongodb-community@7.0`.
