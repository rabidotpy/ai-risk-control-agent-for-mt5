# Project memory

This folder is the **persistent shared context** for any AI coding assistant
(Claude / Copilot / Cursor / etc.) working in this repo. Treat it like a
living engineering notebook — read it before you act, append to it whenever
you learn something a future session shouldn't have to re-discover.

## Files

- [`repo.md`](repo.md) — repo-scoped facts: stack, layout, endpoints, config
  vars, test fixtures, schema gotchas, recurring pitfalls. Always loaded first.
- `session/*.md` (optional) — short-lived working notes for a single
  conversation. Safe to delete after the task closes.
- `decisions/*.md` (optional) — one file per accepted architectural decision
  (lightweight ADR). Append-only; don't rewrite history.

## How to use it (for the assistant)

### At the start of every task

1. Open [`repo.md`](repo.md) — it's authoritative for layout, endpoint
   signatures, env vars, and known gotchas.
2. Skim `decisions/` if your change touches an architectural seam.
3. If `session/` has a file from a recent task on the same area, read it.

### While working

- Don't re-derive what's already documented. Quote `repo.md` instead of
  re-discovering it through grep / file reads.
- If a fact in `repo.md` is wrong, **fix it in the same PR** as the code change.

### Before finishing a task

Append (or update) entries when any of these happen:

- A new module / endpoint / env var is added → update `repo.md` Layout / Endpoints / Config.
- A test count, score denominator, or other "magic number" shifts → update `repo.md`.
- You hit a non-obvious failure mode (encoding, tz, mongomock quirk, tool quirk)
  → add a one-liner under `## Common pitfalls hit` in `repo.md`.
- You make a non-trivial design choice (chose APScheduler over Celery, etc.)
  → drop a short `decisions/NNNN-title.md`.

### Style

- Keep entries terse — bullets, not prose. This file is loaded into the
  assistant's context on every turn; brevity is a feature.
- Prefer code-fenced commands over English descriptions of commands.
- Link to source files with workspace-relative paths so the assistant can
  click through.

### What NOT to write here

- Generated content (lock files, build artefacts).
- Long code snippets — link to the file instead.
- Anything that belongs in user-facing docs (`README.md`, OpenAPI spec).
- Secrets, tokens, customer data.
