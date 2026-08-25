# Forward directive — LLM rotator: push toward real "Auto" routing

**Date:** 2026-08-25
**For:** a Claude Code instance working on the LLM rotator TUI
**Type:** Directive Generator output (per `.claude/CLAUDE.md` § Directive Generator) — cold-start fence, not pre-implemented
**Author note:** written by a different CC session, in the same repo, after the operator asked "how far has my rotator project gone" and got an answer grounded in the actual files (not a guess) — see Prior state below.

## Goal

Move the LLM rotator's model/provider auto-selection from "picks free-then-cheapest" toward something closer to real "Auto" routing (task-aware, context-aware, and reachable from the TUI, not just the CLI) — one concrete, testable slice, not a rewrite.

## Prior state (verified by reading the actual files — not assumed)

The operator believed this was "just a registry... no chatbot interface yet." That's out of date. What's actually there:

| Piece | Path | What it does |
|---|---|---|
| Core index | `tbcc/backend/app/services/llm_model_index.py` | SQLite-backed (`tbcc/.tbcc-run/`, gitignored, operator-machine only). Stores per-provider models (with pricing/context/modality parsed from each provider's `/models` response), credentials for 13 built-ins + custom providers, exhaustion state with quota-vs-transient failure classification (`classify_failure`) and provider-appropriate reset windows (`_quota_reset_window`), a sticky provider/model cursor, and `pick_best_model_for_provider` — free-first, then cheapest-per-million, with an opt-in `--prefer-uncensored` bias. |
| Ranking | same file, `rank_providers_for_cycle` | Skips exhausted/unresolvable providers; sorts by known `usage_remaining` where available (today only OpenRouter), falls back to `DEFAULT_CHAIN` order (`tbcc/backend/app/services/llm_provider_fallback.py`: zlm, deepinfra, together, groq, cerebras, nvidia, mistral, featherless, venice, anythingllm, custom, openrouter — 12 + `openai` = the 13 built-ins). |
| Working single-shot "ask" | `tbcc_cli.py` → `cmd_llm_ask` (`llm ask`) | This is already a real auto-router call, not a stub: resolves the sticky/top-ranked provider, auto-picks the model via `pick_best_model_for_provider` unless `--model` is given, and on a quota-classified failure cycles to the next unexhausted provider and retries once. This *is* the operator's "auto" — it's just CLI-only and single-shot (no conversation memory). |
| TUI #1 | `tbcc/backend/scripts/llm_tui.py` | Textual app, read/cycle-only: table of every known model across providers (ctx/owner/stale/exhausted/usage), `r` = refresh all providers, `n` = advance sticky to next. No ask/chat pane. |
| TUI #2 (bigger) | `tbcc/backend/scripts/operator_tui.py` | Multi-pane: models (reuses the same index), key registration/testing, affiliate links, semantic-scan, self-test. Also no ask/chat pane. |
| Doctrine boundary (hard constraint, not a suggestion) | `llm_model_index.py` module docstring | This index/cursor is explicitly **not** read by `/zeus/v1/ask` (`app/api/zeus_llm.py`) or the MCP `ask_llm` tool — those must stay stateless so an agent calling them gets the caller's explicit provider/model, never whatever the operator's rotator last cycled to. Do not blur this boundary. |
| Naming confirmation | `tbcc/docs/OPERATOR_CAPABILITY_BUS.md` line 14, 23 | TBCC's own docs already call this "the LLM rotator" and list it as a pre-existing engine the capability bus fronts (`operator llm status\|next\|ask\|keys\|models`). |
| Tests | `tests/test_llm_model_index.py` (extensive — failure classification, ranking, sticky/advance, credentials, pricing/modality extraction, model picking), `tests/test_llm_tui.py`, `tests/test_operator_tui.py`, `tests/test_tbcc_cli_llm_ask.py`, `tests/test_tbcc_cli_llm_keys.py` | Mapped in `tbcc/docs/TEST_MAP.md` under "LLM local index / rotator CLI" (note: that row doesn't currently list `test_operator_tui.py` — worth a TEST_MAP fix regardless of which card gets picked). |

**What's genuinely missing** versus a real "Auto" router: no context-length check before picking a model (a large prompt could get routed to a free model with a small context window and truncate/fail silently), no task-complexity signal (always free-then-cheapest, never "this one's hard, use a stronger model"), no per-call cost ceiling, and no ask/chat surface in either TUI — `llm ask` only exists as a CLI command today.

## Reference material (optional, not authoritative)

The operator separately had this repo scanned for "Auto"-routing ideas: `C:\Users\ianmp\Downloads\CL4R1T4S-main\CL4R1T4S-main\` (a collection of leaked/published frontier-LLM-product system prompts). **Checked directly in that scan** (grepped the whole repo for auto-mode/model-selection/routing language, read the actual hits): it does **not** contain a real router's decision algorithm — that logic runs server-side before any model sees a system prompt, so it wouldn't be published this way. The one hit that looked promising (a Codex skill's "for model-selection... fetch the latest-model docs") turned out to be about looking up which model *string* to target via API docs, not a cost/quality routing algorithm. Full writeup, kept open for a second look: `tbcc/docs/handoffs/2026-08-25_cl4r1t4s-prompt-library-scan.md`.

**Do not treat that repo as a source of a routing algorithm** — check it if you want, but go in expecting persona/behavior prompts, not engineering patterns, and verify any specific claim against the actual files before acting on it (that scan's own lesson, learned the hard way from a secondhand summary that turned out to be speculative).

## Issue cards (pick one or more — scoped, not a batch)

1. **Context-length-aware model pick.** `pick_best_model_for_provider` currently ignores `context_length` entirely. Filter out candidates whose `context_length` is smaller than a rough token estimate of the input before applying the free/cheapest sort. Done-condition: a test seeding a catalog where the cheapest/free model has a small context window and the prompt is large asserts it is *not* picked.
2. **Task-tier flag on `llm ask`.** Add `--tier quick|deep` (default `quick` = current free-then-cheapest behavior unchanged). `deep` biases toward highest context_length / a small explicit priority list among priced options — a heuristic, not a classifier. Done-condition: CLI test showing `--tier deep` changes the selection versus default on the same seeded catalog.
3. **Ask/chat pane in a TUI.** Add an interactive prompt input + response pane to `operator_tui.py` (preferred over `llm_tui.py`, since it's the unified surface) that calls the *same* resolve/ask/cycle-on-quota-retry logic `cmd_llm_ask` already has — reuse it (refactor into a shared function both the CLI command and the TUI action call), don't fork a second implementation. This is the actual "chatbot interface" gap the operator flagged. Done-condition: a test exercising the new action/handler against a stubbed runtime, plus documented manual-smoke steps (textual apps aren't meaningfully unit-testable end-to-end).
4. **Per-call cost ceiling.** Optional `--max-cost-per-m` on `llm ask`, filtering `pick_best_model_for_provider` candidates by `price_in_per_m`/`price_out_per_m`. Done-condition: unit test.
5. **TEST_MAP fix.** Add `test_operator_tui.py` to the "LLM local index / rotator CLI" row (or its own row if it's grown past the index alone) — cheap, unblocks nothing but closes a real doc gap noticed while writing this directive.

## Constraints

- Reuse `cmd_llm_ask`'s resolve/cycle-on-quota logic for card 3 — do not re-implement provider resolution or quota-retry in the TUI.
- Preserve the stateless boundary: `/zeus/v1/ask` and the MCP `ask_llm` tool must never read this index/cursor. Any new code stays CLI/TUI-local.
- `textual` is dev-only (`requirements-dev.txt`), not shipped to the island. Don't add it to production requirements.
- Work within the existing 13 built-ins + custom-provider registration path — no new provider onboarding needed for any of these cards.
- Operator-machine only, same as today — nothing here touches bots, Celery, payment/loot, or the island. No deploy step applies.

## Verification

```powershell
cd tbcc/backend
py -3.13 -m pytest tests/test_llm_model_index.py tests/test_llm_tui.py tests/test_operator_tui.py tests/test_tbcc_cli_llm_ask.py tests/test_tbcc_cli_llm_keys.py -x -q --tb=short
```

Manual smoke for card 3 (textual apps need eyes-on): `py -3.13 scripts/tbcc_cli.py operator tui`, drive the new ask pane, confirm a response renders and a forced-quota case cycles provider (can stub via the same monkeypatch pattern `test_tbcc_cli_llm_ask.py` already uses).

## Working agreement

- Plan-only until a card (or set of cards) is picked — do not batch-implement all five.
- Write a reverse `tbcc/docs/handoffs/2026-08-25_llm-rotator-auto-routing-directive_report.md` after the picked phase, stop for operator ACK (Lane C convention, `.claude/CLAUDE.md` § Lane C).
- Do **not** touch `CURRENT_DIRECTIVE.md` — it currently points at the loot-forum-twin thread; this is a separate, independent piece of work.
- Completion gates from `.claude/CLAUDE.md` apply as normal (tests run and reported, git status summarized, halt at >8 files).

## Do not implement yet

This is a directive, not a green light. Stop after reading, pick a card (or say "literal only" / decline), then proceed.

---

## Operator answer — Phase 0 pick (2026-08-25)

The CC instance working this thread asked the operator to choose between "just keep me informed," "commit the 3 new files," "pick up a card myself (1–4)," or "fix the TEST_MAP gap (card 5)." Answer, built with `tbcc-directive-generator`'s issue-card/target-profile schema so it's a directive in its own right, not just a pick:

**Literal ask:** resolve the CC instance's Phase 0 question with a scoped combination, not a single option.
**Ascend:** no — this is a direct decision request, the literal answer is the yield.
**Target:** the Claude Code instance already running this thread (continuity, not cold-start — you've already read everything above).

### Prior state (continuity — verified this session, not assumed)

- `tbcc/docs/TEST_MAP.md`'s "LLM local index / rotator CLI" row lists `test_llm_model_index.py`, `test_llm_tui.py`, `test_tbcc_cli_llm_ask.py`, `test_tbcc_cli_llm_keys.py`, `test_zeus_llm.py` — `test_operator_tui.py` (`tbcc/backend/tests/test_operator_tui.py`, 500 lines, exists in-repo) is missing from that row. Confirmed by reading the row directly.
- `tbcc/docs/handoffs/CURRENT_DIRECTIVE.md` currently points at `2026-08-22_loot-forum-twin-week1.md`, Phase 3, updated 2026-08-23, status "Phases 0–2b complete and ACK'd... Phase 3 is next." Active and un-ACK'd. Confirmed by reading it directly this session.
- The 3 files offered for commit: `.claude/skills/tbcc-integration-scan/SKILL.md` (edited — added an "already-native" axis/tag and a verify-secondhand-claims-before-scoring procedure step), `tbcc/docs/handoffs/2026-08-25_cl4r1t4s-prompt-library-scan.md` (new — open findings doc), and this file itself.

### Issue cards

| # | Symptom | Evidence | Severity | Depends on | Acceptance |
|---|---------|----------|----------|------------|------------|
| I1 | 3 files sit uncommitted, not discoverable to future sessions | `git status` shows all 3 as untracked | P2 | none | commit exists containing exactly those 3 paths (+ this file's edit); `git status` no longer lists them untracked |
| I2 | TEST_MAP row missing a real, existing test file | `tbcc/docs/TEST_MAP.md` "LLM local index / rotator CLI" row, `tbcc/backend/tests/test_operator_tui.py` | P2 | none | that row's test-path list includes `tests/test_operator_tui.py` |
| I3 | No ask/chat surface in either TUI — the actual gap the operator originally flagged ("no chatbot interface yet") | `tbcc_cli.py` `cmd_llm_ask` has the working resolve/ask/cycle-on-quota-retry logic; `operator_tui.py`'s `OperatorTuiApp` has the extension points (`action_refresh_models` etc.) to add a pane to | P1 | I1 recommended first (commit baseline), not a hard blocker | new prompt-input + response pane in `operator_tui.py` calling a *shared* resolve/ask/cycle function refactored out of `cmd_llm_ask` (not duplicated); ≥1 automated test against a stubbed runtime (pattern: `test_tbcc_cli_llm_ask.py`'s monkeypatch style); documented manual-smoke steps |

**Deferred, explicitly not this round:** cards 1 (context-length-aware pick), 2 (task-tier flag), 4 (cost ceiling) from the original directive above. One scoped slice this round (I1–I3), not a batch.

### Constraints & gotchas

- **Judgment ceiling:** MAY implement I1–I3 as scoped. MUST NOT touch `CURRENT_DIRECTIVE.md` (active, un-ACK'd elsewhere — confirmed above) or any doctrine/pricing surface.
- Reuse `cmd_llm_ask`'s resolve/cycle-on-quota logic for I3 — refactor into a shared function both the CLI command and the new TUI action call. Do not fork a second implementation (same constraint as the original directive above).
- `textual` stays dev-only — do not add to production requirements.
- Preserve the stateless boundary: `/zeus/v1/ask` and the MCP `ask_llm` tool must never read the rotator's index/cursor.
- No island deploy, no bot/runtime change.

### Verification

```powershell
cd tbcc/backend
py -3.13 -m pytest tests/test_llm_model_index.py tests/test_llm_tui.py tests/test_operator_tui.py tests/test_tbcc_cli_llm_ask.py tests/test_tbcc_cli_llm_keys.py -x -q --tb=short
```

Manual smoke for I3: `py -3.13 scripts/tbcc_cli.py operator tui` — drive the new ask pane, confirm a response renders and a forced-quota case cycles provider.

### Working agreement

1. Commit I1 + I2 first (small, no test risk) — one or two commits, your call.
2. Implement I3, run the pytest command above.
3. Write the reverse report at `tbcc/docs/handoffs/2026-08-25_llm-rotator-auto-routing-directive_report.md` covering I1–I3.
4. **STOP** after that report for operator ACK before picking up cards 1/2/4.
5. Do not touch `CURRENT_DIRECTIVE.md`.

### Target profile

mode: grind (implement + test) · tools: filesystem + shell + pytest · judgment_ceiling: MUST NOT touch doctrine/pricing/`CURRENT_DIRECTIVE.md` · context: continuity, not cold-start.
