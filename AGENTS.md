# AGENTS.md

Cross-tool entrypoint for AI coding assistants (Claude Code, Cursor,
Copilot CLI, Aider, etc.). All tools that respect `AGENTS.md` should
read this on session start.

## Memory protocol

Persistent project context lives in [`.agents/memory/`](.agents/memory/).

1. **Always read** [`.agents/memory/repo.md`](.agents/memory/repo.md) before acting — it is
   authoritative for stack, layout, endpoints, env vars, schema gotchas,
   and known pitfalls.
2. **Always update** [`.agents/memory/repo.md`](.agents/memory/repo.md) before finishing a task
   when you've added or renamed modules / endpoints / env vars / fixtures,
   shifted a magic number, hit a non-obvious failure mode, or made a
   non-trivial design call.
3. Full protocol & style rules: [`.agents/memory/README.md`](.agents/memory/README.md).

## Quick facts

- Python 3.13, venv at `.venv/` — use `.venv/bin/python` (no `python` on PATH).
- Stack: FastAPI + Tortoise ORM (Postgres prod / SQLite-memory tests) + httpx + anthropic AsyncAnthropic.
- Tests: `.venv/bin/python -m pytest -q` (50 tests, async via pytest-asyncio).
- Local dev (in-memory SQLite, no Postgres needed):
  `DATABASE_URL=sqlite://:memory: .venv/bin/uvicorn app.main:app --port 5050`
- Swagger UI: <http://127.0.0.1:5050/docs>
