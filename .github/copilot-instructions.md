# Copilot / AI assistant instructions

## Memory protocol — READ FIRST

This repo keeps shared engineering notes in [`.agents/memory/`](.agents/memory/).
Treat that folder as **authoritative project context**.

- **Before any task**: read [`.agents/memory/repo.md`](.agents/memory/repo.md). It documents
  the stack, module layout, endpoint signatures, env vars, test fixtures,
  schema gotchas, and common pitfalls. Don't re-derive what's already there.
- **Before finishing a task**: update [`.agents/memory/repo.md`](.agents/memory/repo.md) if you
  added / renamed a module, endpoint, env var, fixture, or test count;
  changed a magic number; hit a non-obvious failure mode; or made a
  non-trivial design call.
- **Style**: bullets, not prose. Link to files. Never store secrets.

Full protocol in [`.agents/memory/README.md`](.agents/memory/README.md).

## Repo quick facts

- Python 3.13, Flask 3, pydantic 2, pymongo + mongomock, APScheduler, anthropic.
- Venv at `.venv/` — no `python` on PATH; always use `.venv/bin/python`.
- Run tests: `.venv/bin/python -m pytest -q`
- Run app locally without Mongo: `MONGODB_URI=mongomock:// .venv/bin/flask --app app.api run --port 5050`
- Swagger UI: http://127.0.0.1:5050/docs
