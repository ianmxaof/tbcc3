# Report: API Pocket Phase 0 — Phase 1 (core registry + CLI)

**Against:** pasted directive "API Pocket Phase 0" (operator, this thread)
**Date:** 2026-08-22

## Summary

Shipped Phase 1 only, as scoped: a PC-local SQLite slot registry, a generic httpx forwarder, and a `tbcc_cli slots` subcommand group (`add|list|show|call|remove|suggest`, `--json` on every path). A freshly-registered slot is immediately callable — no per-vendor SDK. Phase 2 (FastAPI router + extension menu) and Phase 3 (LLM bridge) are untouched per the working agreement's per-phase STOP gate.

## Done — issue cards I1–I3 (P0), I7 (test coverage)

- **I1** `api_slot_registry` persists `{id, category, base_url, auth_env_key, auth_style, openapi_url, method, path_template, headers_json, added_at}` in `tbcc/.tbcc-run/api_slot_registry.sqlite3` (override via `TBCC_API_SLOT_DB`, same pattern as `llm_model_index.py`).
- **I2** `call_slot(id, body=...)` performs a generic httpx request using stored auth, returns `{ok, status, body}` or `{ok: False, error}` — never raises.
- **I3** `tbcc_cli slots add|list|show|call|remove|suggest`, all JSON-capable, stable exit codes (0 success, 1 failure) for TUI subprocess use.
- **I4** (P1, done ahead of schedule since it's one function) `suggest_slot()` classifies pasted key/URL/curl text via `parse_slot_source()` + reused `tbcc_env_secret_store.suggest_env_key()`; unknown APIs fall back to `generic-rest` + a host-derived env key (e.g. `httpbin.org` → `TBCC_HTTPBIN_API_KEY`), never silently drop the operator's input.
- **I7** `tests/test_api_slot_registry.py` (25 tests) + `TEST_MAP.md` row added.

## Files

**New:**
- `tbcc/backend/app/services/api_slot_registry.py` — schema, CRUD, `classify_category()`, `parse_slot_source()`, `suggest_slot()`, `add_slot()`, `call_slot()`. Reuses `tbcc_env_secret_store.normalize_env_key`/`suggest_env_key` so the same key gets the same env var name whether it lands here or in the plain `.env` capture path (per constraint).
- `tbcc/backend/tests/test_api_slot_registry.py` — classify/parse/suggest heuristics, CRUD + id-collision suffixing, OpenAPI-hint success/failure paths, generic caller (bearer/x-api-key/query auth styles, missing-env-var, HTTP error, non-JSON body) — all mocked, no real network.

**Modified:**
- `tbcc/backend/scripts/tbcc_cli.py` — `slots` subparser group + six `cmd_slots_*` handlers; usage examples added to the module docstring.
- `tbcc/docs/TEST_MAP.md` — new row: **API Pocket / slots CLI** → `tests/test_api_slot_registry.py`.

No extension files touched this phase — manifest version bump deferred to Phase 2.

## Design notes / judgment calls (within ceiling)

- **Auth styles implemented:** `bearer` (`Authorization: Bearer {env}`), `x-api-key` (`X-Api-Key: {env}`), `query` (`?api_key={env}`), `none` — matches the Phase 0 auth-pattern constraint exactly, no OAuth.
- **Slot id:** slug from the base URL's first DNS label (see Risk 2 for the `api.<vendor>.tld` edge case), falling back to a slug of the auth env key with `_API`/`_API_KEY` stripped; collision appends `-2`, `-3`, etc. — regardless of whether the id was operator-supplied or auto-derived, so `slots add --id dup` twice never silently overwrites.
- **OpenAPI hint:** fetched once at register time only if `path_template` wasn't already given; picks the first path with a `post` operation, else the first `get`; any fetch/parse failure registers the slot anyway (`base_url`-only) with a `warning` field in the response instead of failing the whole `add`.
- **Auth resolution is env-only:** `call_slot()` reads `os.getenv(auth_env_key)` — it never reads `.env` itself. This matches `llm_model_index.py`'s posture and relies on `load_tbcc_dotenv()` already having run (true for both `tbcc_cli.py` and, in Phase 2, FastAPI startup).

## Verification

```
cd tbcc/backend
py -3.13 -m pytest tests/test_api_slot_registry.py tests/test_tbcc_env_secret_store.py -x -q --tb=short
32 passed in 0.93s
```

Manual CLI smoke (real subprocess, not pytest):

```
py -3.13 scripts/tbcc_cli.py slots add --id smoke-echo --category generic-rest --base-url https://httpbin.org --auth-env-key TBCC_SMOKE_KEY --path /post --method POST --auth-style none --json
py -3.13 scripts/tbcc_cli.py slots show smoke-echo --json
py -3.13 scripts/tbcc_cli.py slots remove smoke-echo --json
py -3.13 scripts/tbcc_cli.py slots suggest "sk-or-abcdefghijklmnopqrstuvwx" --json   # → id=openrouter, category=llm
```

`add` → `show` → `remove` round-tripped correctly through the real CLI process (registry persisted to a throwaway `TBCC_API_SLOT_DB`, cleaned up after). `slots call smoke-echo --body '{"hello":"pocket"}'` reached the httpx request layer and failed with `getaddrinfo failed` — **this sandbox has no outbound internet**, not a code defect; `call_slot()` degraded to a clean `{"ok": false, "error": ...}` instead of throwing, which is the behavior the acceptance criteria actually cares about. Could not verify the httpbin 200-echo response itself from this machine — flagging per the "say so explicitly" rule rather than claiming full success.

## Risks / known rough edges

1. **Untested against real network.** The generic caller's happy path (a live 200 response) is only verified via mocked `httpx.request` in pytest — the manual smoke stopped at DNS resolution. Recommend the operator re-run the `slots call smoke-echo` command from a machine with internet before trusting it in the TUI.
2. **Hostname-based id derivation picks the first DNS label, not necessarily the recognizable brand name** — e.g. `api.openrouter.ai` derives id `api`, not `openrouter` (confirmed in the `suggest_slot` test — see `test_suggest_slot_generates_id_and_category`). This only bites bare-key suggestions with a `api.<vendor>.tld`-shaped URL; `httpbin.org` and similar single-label hosts derive correctly. Operator can always override with `--id`. Not fixed here since it wasn't flagged as an issue card and changing the heuristic risks second-guessing the directive's stated acceptance criteria — flagging for an explicit call instead of guessing.
3. **Windows/Git Bash path-conversion trap for anyone testing manually:** `--path /post` gets silently rewritten to a Windows path (`C:/Program Files/Git/post`) by Git Bash's MSYS path conversion unless `MSYS_NO_PATHCONV=1` is set first. Not a code issue — the CLI stores whatever string argparse hands it — but worth calling out since it wasted a smoke-test cycle here and will bite the operator too.

## Deferred (per phased scope — not started)

- **Phase 2:** `/tools/slots/...` FastAPI router, extension context-menu item + clipboard-parse handler, manifest version bump.
- **Phase 3:** LLM-category bridge to `llm_model_index.set_credential()`.
- Out of scope per directive (untouched): island deploy/sync, per-vendor SDK codegen, MCP tool registration, DOM-only "text shrink" userscript heuristics, any payment/loot doctrine.

## Next steps

| What | Unblocks | Reversibility | Evidence |
|------|----------|----------------|----------|
| Re-run `slots call smoke-echo` from a networked machine to confirm the real httpbin 200 echo | self (closes Risk 1) | trivial-revert | `py -3.13 scripts/tbcc_cli.py slots call smoke-echo --body '{"hello":"pocket"}' --json` |
| ACK this report, then proceed to Phase 2 (FastAPI router + extension menu) | deploy (extension ships to operator browser) | trivial-revert | `/cc-report` ACK in Cursor |
| Decide the hostname-id heuristic (Risk 2) before it ships in the extension menu, where operators won't pass `--id` | other-work | trivial-revert | operator call, not a code change yet |

Orthogonal to `tbcc/docs/SPRINT_STATE.md`'s current goal — API Pocket is a new operator-tooling vertical, not a continuation of the sprint's tracked work.
