---
description: Persistent project memory — read at task start, update before finishing.
applyTo: "**"
---

# Project memory protocol

This repo keeps long-lived engineering notes in [`.agents/memory/`](../../.agents/memory/).
Treat that folder as **authoritative shared context** across all AI coding
sessions in this workspace.

## When you start any task

1. Read [`.agents/memory/repo.md`](../../.agents/memory/repo.md) first. It is the source of
   truth for stack, layout, endpoints, env vars, schema gotchas, and known
   pitfalls. Do not re-derive what's already documented.
2. If the task touches an architectural seam, skim `.agents/memory/decisions/`.
3. Quote facts from memory instead of re-discovering them through search.

## While you work

- Prefer the workflows already documented (e.g. run the venv binary
  `.venv/bin/python`, use `MONGODB_URI=mongomock://` for local Flask runs).
- If a fact in memory is wrong, fix the memory file in the same change as
  the code.

## Before you finish a task — UPDATE memory if any of these are true

- Added / removed / renamed a module, endpoint, env var, or fixture
  → update `repo.md` Layout / Endpoints / Config.
- Test count, score denominator, or other "magic number" shifted
  → update the relevant section of `repo.md`.
- Hit a non-obvious failure mode (timezone, encoding, tool quirk, mongomock
  edge-case, OS limitation) → add one bullet under `## Common pitfalls hit`.
- Made a non-trivial design choice → drop a short
  `.agents/memory/decisions/NNNN-title.md` (one-paragraph ADR).

## Style rules for memory files

- Bullets, not prose. Memory is loaded into context every turn; brevity is a feature.
- Prefer code-fenced commands over English descriptions of commands.
- Link to source files with workspace-relative paths.
- Never put secrets, tokens, or customer data in memory.

## Forbidden

- Don't paste large code snippets into memory — link to the file instead.
- Don't duplicate user-facing docs (README, OpenAPI spec) into memory.
- Don't silently change a documented invariant; update the memory note in
  the same edit.
