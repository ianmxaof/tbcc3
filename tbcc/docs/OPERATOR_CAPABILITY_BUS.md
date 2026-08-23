# Operator capability bus (v0)

One discoverable CLI hub for operator tools that otherwise live scattered across Cursor skills and `tbcc_cli.py`. Lives outside this repo, at `%USERPROFILE%\.cursor\skills\operator-cli\` — this doc exists so a TBCC-focused session (Cursor or Claude Code) knows it's there without having to know that path already.

## What it is

- `operator_cli.py` — thin dispatcher. `operator <skill> <args>` either runs a skill's own script directly (`status: live`) or forwards the args unchanged to `tbcc_cli.py <skill> <args>` (`status: delegate`).
- `registry.json` — the machine-readable skill list: `id`, `description`, `entry` (script/subcommand path), `corpora[]` (local files worth reading for context), `status`.

```
operator list                              # what's registered
operator semantic-scan --json <path|url>   # live: docs-vs-behavior / hidden-unicode / injection-bait scan
operator research feed-add|feed-list|scan  # delegate: RSS/Atom research scanner (tbcc_cli.py research)
operator llm status|next|ask|keys|models   # delegate: local LLM provider/model index (tbcc_cli.py llm)
operator slots add|list|call|…             # delegate: API Pocket REST service-slot registry (tbcc_cli.py slots)
```

## What it deliberately is not

**Not a Context7-style cloud doc source.** `corpora[]` entries are local file paths (this repo, this machine's skills tree) — nothing is fetched from a hosted/versioned docs index, and nothing here is shared beyond this machine. It's a pointer list so an agent can find a skill's own context (its source, its data file, its Hermes SKILL.md) in one lookup instead of a `find`/`grep` round trip — "local transferable context," not a docs product.

**Not a new engine.** `research`, `llm`, and `slots` were built and working before this bus existed — the research scanner (`app/services/research_scanner.py`), the LLM rotator (`app/services/llm_model_index.py`), and API Pocket (`app/services/api_slot_registry.py`, the operator's "mechanical arm" for ad-hoc REST calls) all predate this. The bus adds one discoverable front door and, for research, one new capability those engines didn't have yet: `feed-add`/`feed-list` to manage `research_scanner_sources.json` from the CLI instead of hand-editing JSON.

**Not a work queue.** Each `operator <skill>` call is a single synchronous subprocess forward — no orchestration, scheduling, or multi-agent coordination layer. That's explicitly out of scope for v0.

## Provenance

Built 2026-08-22 per Cursor directive (`tbcc/docs/handoffs/2026-08-22_operator-capability-bus-v0.md`), following the semantic-deception-detector hardening work (`2026-08-22_semantic-deception-scanner-hardening*.md`, `*-phase3*.md`) that established the `operator-cli` hub pattern this reuses.
