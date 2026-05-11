# AI Risk Control Agent for MT5

FastAPI + Tortoise ORM service that runs Claude-backed risk analysis over
MT5 broker snapshots. Each `/analyse_risk` call returns one finding per
risk type per account, plus an updated rolling behaviour summary.

## Stack

- Python 3.13, FastAPI, Pydantic 2, Tortoise ORM (Postgres / SQLite),
  Anthropic SDK, httpx, uvicorn.
- Tests: pytest + pytest-asyncio, SQLite in-memory.

## Run

```bash
# Install (uv)
uv sync

# Boot the API (defaults: 127.0.0.1:5050, sqlite in-memory)
uv run app

# Custom host/port/reload
HOST=0.0.0.0 PORT=5050 RELOAD=true uv run app

# Swagger UI
open http://127.0.0.1:5050/docs
```

Set `ANTHROPIC_API_KEY`, `DATABASE_URL`, `CALLBACK_URL`, and `LOG_LEVEL`
in `.env` (see `.env.example`).

## Test

```bash
.venv/bin/python -m pytest -q
```

## Endpoints

- `POST /analyse_risk` — body: `{"snapshots": [AccountSnapshot...], "include_history": bool|null}`. Returns `list[RiskFinding]`.
- `GET  /analyses?mt5_login=&start_time=` — persisted evaluations for a window.
- `GET  /history?mt5_login=` — rolling behaviour summary per risk type.
- `GET  /healthz`

## Project memory

Long-lived engineering notes live in [`.agents/memory/`](.agents/memory/).
Read [`repo.md`](.agents/memory/repo.md) before non-trivial work.
