# Report: LLM rotator auto-routing directive — Phase 0 (I1–I3)

**Against:** `tbcc/docs/handoffs/2026-08-25_llm-rotator-auto-routing-directive.md`, specifically its appended "Operator answer — Phase 0 pick" section (I1–I3; cards 1/2/4 explicitly deferred)
**Date:** 2026-08-25
**Session:** the Claude Code instance that built `operator_tui.py` this thread — continuity, not cold-start

## Summary

Committed the directive's own 3 files plus the TEST_MAP fix (I1+I2), then implemented I3: an Ask pane in `operator_tui.py` backed by a new shared function, `llm_model_index.ask_with_rotation()`, extracted from `cmd_llm_ask` so the CLI and the TUI call one implementation instead of two. All directed pytest paths pass (83/83). Stopping here per the Working agreement — not touching cards 1/2/4 or `CURRENT_DIRECTIVE.md`.

## Done

- **I1** — Commit `caeaf60`: the 3 files named in the directive (`tbcc-integration-scan/SKILL.md`, the CL4R1T4S scan doc, the directive itself).
- **I2** — Same commit: `TEST_MAP.md`'s "LLM local index / rotator CLI" row now lists `tests/test_operator_tui.py`, plus a note on the shared `ask_with_rotation` function. The "Unified operator TUI" row was also updated to mention the new Ask pane.
- **I3** — Extracted `cmd_llm_ask`'s resolve → ask → cycle-on-quota-retry loop into `app/services/llm_model_index.py::ask_with_rotation()` (never raises; returns `{"ok": True, "provider", "model", "reply", "notices"}` or `{"ok": False, "error", "notices"}` — `notices` carries human-readable side-events like a mid-call provider cycle, so each caller renders them its own way). `cmd_llm_ask` is now a thin wrapper: stdin handling + stdout/stderr shape around one call to the shared function. Added an **Ask** tab to `operator_tui.py` (now the first tab) — prompt `TextArea`, **Ask** button (runs in a worker thread, same pattern as the Scan pane), a status line showing `provider/model` or the error, a `Log` showing the reply and any cycle notices, and a **Copy reply** button (`copy_to_clipboard`, same OSC 52 mechanism as the Models/Affiliate copy buttons already in this file).

## Design notes

- **Why `llm_model_index.py` and not a new module:** it already imports from `llm_completions.py` (one-directional, no cycle risk) and already owns every other piece the retry loop touches (`get_sticky`, `set_sticky`, `advance_to_next`, `rank_providers_for_cycle`, `record_failure`, `resolve_runtime_for_rotator`, `pick_best_model_for_provider`). `ask_with_rotation` calls them as bare module-global names (same file), which is why the existing tests' monkeypatches (`"app.services.llm_model_index.get_sticky"` etc.) kept working with zero changes — Python resolves those names from the module's `__dict__` at call time, and `monkeypatch.setattr` on that dotted path mutates the same dict entry a sibling function reads.
- **`complete_chat_text_sync` stayed a function-local import** inside `ask_with_rotation` (not hoisted to module top), deliberately mirroring `cmd_llm_ask`'s original pattern — `test_tbcc_cli_llm_ask.py` patches `"app.services.llm_completions.complete_chat_text_sync"` (the source module), which only works if the consumer re-imports the name fresh at call time rather than binding it once at module load. Verified this by running the existing test file unchanged after the refactor: 41/41 passed, no test edits needed.
- **Human-facing strings moved out of the shared function.** The original `cmd_llm_ask` printed straight to stderr mid-logic (`"{provider!r} no longer configured..."`, `"...cycling to next provider…"`). `ask_with_rotation` collects these as plain strings in a `notices` list instead — the CLI prints them to stderr (preserving the exact existing test assertions, e.g. `"no longer configured" in capsys.readouterr().err`), the TUI writes them into the Ask pane's `Log`. Neither caller re-implements the retry logic itself.
- **Ask pane placement:** made it the first tab (previously Models was first) since it's the headline gap the operator flagged ("no chatbot interface yet"). This shifted the *default* active tab, which broke one existing test (`test_hover_over_model_row_sets_tooltip_to_full_id` — Pilot's simulated mouse hover can't land on a widget hidden behind the now-inactive Models pane). Fixed by having that test explicitly switch `TabbedContent.active` to `"pane-models"` first; not a behavior regression, just a test that had been implicitly relying on tab order.
- **No conversation memory** — each Ask-pane submission is a single independent call, same as `llm ask` today. The directive's Prior state section already logged this as the CLI's existing limitation; I3's acceptance condition was an ask/chat *surface*, not turn-taking memory, so didn't add it.

## Files

**New:**
- `tbcc/backend/scripts/operator_tui.py` — **not new this report**, but flagging: this file (and its test file) predate I3 and have never been committed in this thread at all, across several earlier feature rounds (Keys/Affiliate/RSS/Scan panes, the banner, the 62×28 layout fix). I3 added ~35 lines to it (the Ask pane + 3 handler methods) on top of that pre-existing uncommitted work.

**Modified:**
- `tbcc/backend/app/services/llm_model_index.py` — +100/−0: new `ask_with_rotation()` appended after `pick_best_model_for_provider` (its last dependency in file order).
- `tbcc/backend/scripts/tbcc_cli.py` — `cmd_llm_ask` shrunk from ~99 lines to ~30; net diff +150/−67 across the two files combined.
- `tbcc/backend/tests/test_operator_tui.py` — +7 tests for the Ask pane (reply+status, error, quota-cycle notice rendering, empty-prompt guard, copy-with-reply, copy-without-reply) and 1 fixed pre-existing test (tab-order dependency above); now 31 tests total, up from 24.

## Verification

```
cd tbcc/backend
py -3.13 -m pytest tests/test_llm_model_index.py tests/test_llm_tui.py tests/test_operator_tui.py tests/test_tbcc_cli_llm_ask.py tests/test_tbcc_cli_llm_keys.py -x -q --tb=short
83 passed
```

Manual smoke (per the directive): `py -3.13 scripts/tbcc_cli.py operator tui` launched clean, no traceback, 5s run (this sandbox has no real terminal to drive interactively or a live LLM key to actually call). The **cycle-on-quota** path itself is exercised two ways instead: `test_tbcc_cli_llm_ask.py::test_cycles_to_next_provider_on_quota_and_succeeds` drives the real `ask_with_rotation` logic through a simulated quota failure end-to-end (asserts both providers were actually called, in order, and the sticky cursor lands on the second one); `test_operator_tui.py::test_ask_pane_shows_cycle_notice_in_log` verifies the TUI pane renders that cycle's notice text. Recommend the operator still eyeball the real pane once with a live key, since Textual apps aren't meaningfully unit-testable end-to-end for actual rendering.

## Risks / known rough edges

1. **Nothing from I3 is committed.** Per the directive's Working agreement, only I1+I2 were explicitly called out as a commit step; I3 (and all of `operator_tui.py`'s prior uncommitted work from earlier this thread) is left in the working tree for your review. `git status` currently shows `llm_model_index.py` and `tbcc_cli.py` modified, `operator_tui.py` and `tests/test_operator_tui.py` untracked.
2. **Scope note:** this report's own diff touches 4 files (2 modified + 2 untracked-but-touched) — under the 8-file halt gate, but `operator_tui.py`'s total accumulated uncommitted history across this whole thread is much larger than I3 alone; a future commit covering "all of operator_tui.py" should account for that, not just this round's diff.
3. **Textual apps aren't unit-testable end-to-end** — the Ask pane's tests all stub `ask_with_rotation` itself (never touching real network/LLM calls), so they verify the TUI's *display* logic, not that a real API key + real provider actually answers correctly. That's an inherent gap in this whole test suite (same caveat applies to every other pane already), not new here.

## Next steps

| What | Unblocks | Reversibility | Evidence |
|------|----------|----------------|----------|
| ACK this report so I3 (and the rest of `operator_tui.py`) can be committed | discoverability, deploy-adjacent (operator-machine only, no island involved) | trivial-revert (pre-merge branch) | `git log --oneline -1` after commit |
| Drive the Ask pane by hand once with a real key (`operator tui` → Ask tab → type a prompt → Ask) | self — closes the "not manually driven" gap noted above | trivial-revert | a reply renders; forcing a 429 (or just watching real quota) shows a cycle notice in the log |
| Pick up card 1, 2, or 4 from the original directive (context-length pick / task-tier flag / cost ceiling) — separate, smaller slices | orthogonal to `SPRINT_STATE.md`'s current goal — this whole thread is devops tooling, not sprint-tracked product work | trivial-revert (pytest-gated) | same Verification pytest path in the original directive |

**STOP** — per the Working agreement, waiting for operator ACK before touching anything else.
