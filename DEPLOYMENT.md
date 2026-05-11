# Deployment guide

Audience: an AI agent (or human) deploying this service for the first
time, or upgrading from the pre-rewrite (Phase B) version.

## 1. What changed from Phase B

| Concern        | Before (Phase B)                    | Now                                          |
| -------------- | ----------------------------------- | -------------------------------------------- |
| Web framework  | Flask 3                             | FastAPI 0.115+                               |
| Server         | gunicorn / `flask run`              | uvicorn (`uv run app`)                       |
| Storage        | MongoDB (pymongo / mongomock)       | Postgres via Tortoise ORM (SQLite for tests) |
| Scheduling     | APScheduler in-process              | Removed — no scheduled scans                 |
| Ingestion      | Alex client + raw-pulls cache       | Removed — caller POSTs snapshots directly    |
| LLM client     | `anthropic.Anthropic` (sync)        | `anthropic.AsyncAnthropic`                   |
| Body shape     | Several permissive shapes           | Single Pydantic envelope (see §4)            |
| History rules  | `trend_*`, `lookback_*` sub-rules   | Removed — replaced by AI rolling summary     |
| Entrypoint     | `flask --app app.api run`           | `uv run app` → `app.__main__:main`           |
| Migrations     | None (Mongo)                        | None yet — `generate_schemas=True` on boot   |
| Tests          | 114 (pytest, sync)                  | 50 (pytest-asyncio, SQLite-memory)           |
| Logging        | ad-hoc `print` / Flask defaults     | `app.logging_config.configure_logging()`     |

**Public API surface change** (breaking): `POST /analyse_risk` now
accepts only one body shape. Bare snapshot dicts and bare lists are
rejected with FastAPI 422 (not the old custom 400+`index`).

## 2. Runtime requirements

- Python **3.13** (pinned in `.python-version`).
- A Postgres instance for production (any 13+; uses `asyncpg`).
- Outbound HTTPS to `api.anthropic.com`.
- Outbound HTTPS to whatever `CALLBACK_URL` points at (optional).

No Redis, no Mongo, no scheduler, no message broker.

## 3. Environment variables

Copy `.env.example` → `.env` and fill in. All keys:

| Var                        | Required | Default                  | Notes                                                                 |
| -------------------------- | -------- | ------------------------ | --------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`        | yes      | —                        | Production key. Tests inject a fake evaluator, no key needed.         |
| `CLAUDE_MODEL`             | no       | `claude-opus-4-7`        | Override per env. `.env.example` shows `claude-sonnet-4-6`.           |
| `CLAUDE_MAX_TOKENS`        | no       | `1024`                   | Per-call ceiling.                                                     |
| `CALLBACK_URL`             | no       | empty                    | If set, POSTs the analysis result. Empty = skip (logged as `skipped`).|
| `CALLBACK_TIMEOUT_SECONDS` | no       | `10`                     | Float seconds for httpx.                                              |
| `DATABASE_URL`             | yes      | `sqlite://:memory:`      | Use `postgres://user:pass@host:5432/db` in prod.                      |
| `INCLUDE_HISTORY_DEFAULT`  | no       | `true`                   | Per-request `include_history` in the body overrides this.             |
| `LOG_LEVEL`                | no       | `INFO`                   | One of DEBUG/INFO/WARNING/ERROR.                                      |
| `HOST`                     | no       | `127.0.0.1`              | Read by `app/__main__.py`. Set to `0.0.0.0` in containers.            |
| `PORT`                     | no       | `5050`                   | "                                                                     |
| `RELOAD`                   | no       | `false`                  | Dev-only auto-reload.                                                 |

## 4. HTTP contract

- `GET  /healthz` → `{"status":"ok"}`
- `POST /analyse_risk` — body **must** be:
  ```json
  {
    "snapshots": [ { /* AccountSnapshot */ } ],
    "include_history": true
  }
  ```
  Returns `200 list[RiskFinding]`. Bad payloads → `422` with FastAPI's
  standard `detail: [{loc, msg, type}]` array.
- `GET  /analyses?mt5_login=<int>&start_time=<iso8601>` → persisted
  evaluations for that window; `404` if none.
- `GET  /history?mt5_login=<int>` → rolling behaviour summary per risk
  type (one row per `(mt5_login, risk_key)`).
- `GET  /docs` — Swagger UI. All schemas live in `components/schemas`
  (`AccountSnapshot`, `AnalyseRiskRequest`, `RiskFinding`, etc.).

## 5. Local run (no Postgres)

```bash
uv sync
DATABASE_URL=sqlite://:memory: uv run app
# → http://127.0.0.1:5050/docs
```

## 6. Production deploy — bare metal / VM

```bash
# Once
git clone https://github.com/rabidotpy/ai-risk-control-agent-for-mt5.git
cd ai-risk-control-agent-for-mt5
uv sync --no-dev

# Per release
cp .env.example .env   # then edit with real values
HOST=0.0.0.0 PORT=5050 LOG_LEVEL=INFO uv run app
```

Behind a reverse proxy, terminate TLS at nginx/Caddy and forward to
`127.0.0.1:5050`. Health probe: `GET /healthz`.

For systemd, drop a unit like:

```ini
[Unit]
Description=AI Risk Control Agent
After=network.target

[Service]
Type=simple
User=risk
WorkingDirectory=/srv/ai-risk-control-agent-for-mt5
EnvironmentFile=/srv/ai-risk-control-agent-for-mt5/.env
ExecStart=/usr/local/bin/uv run app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 7. Production deploy — Docker

No Dockerfile is committed. Minimal example:

```dockerfile
FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ ./app/
ENV HOST=0.0.0.0 PORT=5050 LOG_LEVEL=INFO
EXPOSE 5050
CMD ["uv", "run", "app"]
```

Pass `ANTHROPIC_API_KEY`, `DATABASE_URL`, and `CALLBACK_URL` via env
(`docker run -e ...` or k8s `Secret`). Mount nothing — service is
stateless; all state lives in Postgres.

## 8. Database

- Schema is created automatically by Tortoise's `generate_schemas=True`
  during FastAPI lifespan startup.
- **No Aerich migrations yet.** First production deploy: point at an
  empty database; subsequent additive changes are auto-applied. For
  destructive schema changes you must add Aerich (`uv add aerich`) and
  manage migrations explicitly before that change ships.
- Tables (see `app/models/analysis.py`):
  - `analysis_run` — one row per `/analyse_risk` call.
  - `risk_evaluation` — one row per (run, snapshot, risk_key).
  - `risk_history_summary` — rolling AI summary, unique on
    `(mt5_login, risk_key)`.

## 9. Logging

- Configured in `app/logging_config.py`; called from `app/__main__.py`
  and once at module load in `app/main.py`.
- Single-line format:
  `2026-05-12 01:48:16,760 INFO  app.main :: lifespan: Tortoise ready`.
- `httpx`, `httpcore`, `tortoise`, `asyncio` are pinned to WARNING.
- For JSON logs in prod, replace the `Formatter` in
  `app/logging_config.py` with a JSON formatter (e.g. `python-json-logger`).
  No code outside that file needs to change.

## 10. Tests / CI

```bash
uv sync --extra dev
.venv/bin/python -m pytest -q     # 50 tests, ~0.2s, no network
```

Tests use SQLite-memory and a `FakeEvaluator` — they do not require
`ANTHROPIC_API_KEY` or any external service. Safe to run in CI without
secrets.

## 11. Tortoise + FastAPI gotcha (already fixed — do NOT regress)

Tortoise 1.x keeps connections in a per-task `ContextVar`. FastAPI's
lifespan runs in a different task than request handlers, so calling
`Tortoise.init()` directly in lifespan causes:

```
RuntimeError: No TortoiseContext is currently active.
```

The fix in `app/main.py` is:

```python
from tortoise.contrib.fastapi import RegisterTortoise

async with RegisterTortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=True,
    add_exception_handlers=False,
    _enable_global_fallback=True,   # critical
):
    yield
```

`_enable_global_fallback=True` is what makes request-task code see the
DB. Tests are different — they run in the same task as the ASGI
transport, so they keep calling `init_db()` directly via the `db`
fixture in `tests/conftest.py`.

## 12. Post-deploy smoke test

```bash
curl -s http://HOST:PORT/healthz
# → {"status":"ok"}

curl -s -X POST http://HOST:PORT/analyse_risk \
  -H 'content-type: application/json' \
  -d '{"snapshots":[]}'
# → []        (no LLM call, empty findings list)
```

Then open `/docs` and confirm `components.schemas` shows
`AccountSnapshot`, `AnalyseRiskRequest`, `RiskFinding`, etc. — no red
resolver errors.

## 13. Where to read next

- `.agents/memory/repo.md` — authoritative engineering notes, common
  pitfalls, score arithmetic, removed components.
- `AGENTS.md` — quick facts for AI assistants.
- `app/api/routes.py` — endpoint signatures.
- `app/services/analysis.py` — orchestrator (per-risk loop, persistence,
  summary upsert).
