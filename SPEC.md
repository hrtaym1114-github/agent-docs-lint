# SPEC — agent-docs-lint (MVP v0.1)

> Scout-recommended 2026-10-05 JST. Build slot 2026-10-06 (1/day).
> Public GitHub: `hrtaym1114-github/agent-docs-lint`
> Attribution: `hrtaym1114` only (never real names).
> Process: Tool Factory Codex redesign — Build ∥ Announce.

## Problem

Agent/coding-agent repos accumulate docs (`AGENTS.md`, `CLAUDE.md`, rules, agent/skill files) that drift: dead path refs, hard-coded model/plan names, orphan agent/skill files nobody references. Manual cleanup is painful — on 2026-10-03 the Amu Lab vault needed a hand audit that:

- Removed dead refs from `CLAUDE.md` (nonexistent `notion-up.md`, stale production-queue pointer)
- Fixed rules pointing at renamed commands (`/blog01-generate-article` → `/blog-write`) and invalid style tokens
- Archived 6 unreferenced `paperbanana-*` agents
- Stripped hard-coded model/plan strings from rules in favor of a canonical pointer

That work should be a **repeatable zero-LLM CLI** for CI and local preflight.

## Who hurts

- Agent-ops people maintaining AGENTS.md / CLAUDE.md / `.cursor/rules` / `.claude/agents|skills`
- Manufacturing × shopfloor AI / local-LLM / agent-ops niche users who keep docs as the source of truth

## Why now

- Real ops pain already paid once (vault commits `8aa0af61`, `272f39ad`)
- External signal: “Agents don't need memory, they need documentation”
- Fits niche: agent ops hygiene, no cloud, no GPU

## Attractiveness (must pass)

1. 30s demo: run against `fixtures/demo` → see real FAIL findings
2. Extracted from real ops (not invented)
3. One-line install: `pip install git+https://github.com/hrtaym1114-github/agent-docs-lint.git`
4. GIF/demo video: out of scope for v0.1 (README shows a runnable demo command instead)

## MVP

CLI `agent-docs-lint [PATH]` (default `.`):

### Scan roots (auto-discover under PATH)
- `AGENTS.md`, `CLAUDE.md` (and case variants)
- `.cursor/rules/**` (`.md`, `.mdc`)
- `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`
- `.agents/skills/**`, `agents/**` (markdown agent defs)
- Optional: `AGENTS.md` / `CLAUDE.md` anywhere one level deeper if present

### Checks
1. **dead_ref** — markdown links / backtick path-like refs / slash-commands that point to missing files (relative to repo root or the referencing file). Also flag obvious missing command targets when a `/command-name` is documented but no matching skill/command file exists under known skill dirs (best-effort).
2. **model_name** — hard-coded / outdated model or plan tokens from a **configurable list** (default list includes common stale names like `gpt-4`, `gpt-4o`, `claude-3-opus`, `claude-3.5-sonnet`, `o1-preview`, plus plan words like `ChatGPT Plus` when used as “always use X”). Allowlist / config can disable entries.
3. **unreferenced_agent** — agent/skill markdown files under agent/skill dirs that are never mentioned by name (filename stem) from AGENTS.md / CLAUDE.md / registries / other agents. Templates (`_*`) and `README.md` skipped.
4. **broken_anchor** — local markdown links with `#anchor` where the heading slug is missing in the target file (same-file or relative).

### Output
- Human text (default): file:line, rule id, message
- `--json`: machine-readable list of findings
- Exit **0** if no findings (or only allowed severities); **1** if any error-severity finding (default: all rules are error). `--warn-only` → always 0 after print.

### Config (optional)
- `agent-docs-lint.toml` or `.agent-docs-lint.toml` at root, or `--config PATH`
- Keys: `model_names = [...]`, `ignore_paths = [...]`, `disable_rules = [...]`, `extra_scan_globs = []`

### Non-goals
- LLM / network calls
- Auto-fix / rewriting files
- Full markdown link checker for http(s) URLs
- Parsing every proprietary agent YAML schema
- GIF production
- No `.github/workflows/*` in this repo (document Action snippet in README instead — publisher lacks workflow scope)

## Package
- Python ≥ 3.10, stdlib only at runtime
- MIT, author `hrtaym1114`
- `pyproject.toml` + `src/agent_docs_lint/`
- tests with pytest; fixtures/demo with intentional failures
- README: English primary + short Japanese section; install; usage; example output; GitHub Action snippet; runnable demo command

## Demo script (30s)
```sh
pip install -e .
agent-docs-lint fixtures/demo
# expect nonzero exit and findings: dead_ref, model_name, unreferenced_agent, broken_anchor
agent-docs-lint fixtures/demo --json | head
```

## Acceptance
- `pytest -q` green
- `pip install .` works; entry point `agent-docs-lint`
- fixtures/demo fails with ≥1 finding per rule family
- README has Action YAML example under `docs/` or README (not committed as workflow)
- No secrets, no real personal names
