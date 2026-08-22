# Report: API Pocket Phase 0 — Phase 2 (FastAPI router + extension menu)

**Against:** pasted directive "API Pocket Phase 2" (operator, this thread), builds on Phase 1 `0adc19b`
**Date:** 2026-08-22

## Summary

Shipped Phase 2 as scoped: `/tools/slots` FastAPI router over the existing registry, an extension "Load API from clipboard" context-menu item + handler that registers a slot in one round trip, the `api.<vendor>.tld` hostname-id fix (I3), and the manifest patch bump. Phase 3 (LLM-index bridge) is untouched, per the working agreement's STOP gate.

## Done — issue cards I1–I6

- **I1** `app/api/tools_slots.py` mounted at `/tools/slots`: `GET ""` (list), `POST "/suggest"`, `POST ""` (register), `GET "/{id}"`, `POST "/{id}/call"`, `DELETE "/{id}"`. Thin wrapper — no business logic duplicated outside `api_slot_registry.py`.
- **I2** New menu `tbccLoadApiSlotSelection` ("TBCC: Load API from clipboard") next to the existing `tbccCaptureSecretSelection` in `tbcc-context-menu-items.js`; `tbccLoadApiSlotFromSelection()` in `background.js` POSTs the selected text to `/tools/slots`, toasts `slot <id> ready` on success, and falls back to the existing key-capture picker (`tbccOpenCaptureSecretPrompt`) on a 400/422 or a network error — mirrors `tbccCaptureSecretFromSelection`'s exact fallback shape.
- **I3** `_slot_id_from_hint()` and `_fallback_env_key()` now share one `_brand_label_from_host()` helper: drops a leading `api.` subdomain when a real second label exists (`api.openrouter.ai` → `openrouter`), leaves two-label hosts alone (`httpbin.org` → `httpbin`). Fixed both functions, not just the one named in the issue card — they had the identical bug (see Phase 1 report Risk 2) and diverging would have meant a slot's auto-id and its auto env-key label disagreeing on the same host.
- **I4** `POST /tools/slots` (register) does the full chain in one call: `suggest_slot()` → `write_env_secret()` → `backup_credential_manager()` → `add_slot()`. Rejects with 400 before touching `.env` if the parsed value doesn't `looks_like_api_key()`.
- **I5** `tests/test_tools_slots_api.py` — 9 tests via `TestClient(app)`: list/suggest/register/get/call/remove, 404s, register→remove round trip, register-rejects-junk. `backup_credential_manager` is stubbed out for every test (see Risks — it would otherwise touch the real Windows Credential Manager).
- **I6** `manifest.json`: **1.40.48 → 1.40.49**.

## Files

**New:**
- `tbcc/backend/app/api/tools_slots.py` — router + 3 Pydantic bodies (`SuggestSlotBody`, `RegisterSlotBody`, `CallSlotBody`).
- `tbcc/backend/tests/test_tools_slots_api.py` — route coverage, no real network/CredMan/`.env`.

**Modified:**
- `tbcc/backend/app/main.py` — added `tools_slots` to the big API import line + `app.include_router(tools_slots.router, prefix="/tools/slots", ...)` next to `extension_capture_secret`.
- `tbcc/backend/app/services/api_slot_registry.py` — extracted `_brand_label_from_host()`; `_slot_id_from_hint()` and `_fallback_env_key()` both call it now.
- `tbcc/backend/tests/test_api_slot_registry.py` — updated the one assertion that depended on the old `api` id, added 4 new tests for the fixed heuristic (`_slot_id_from_hint` directly, plus the shared-heuristic consistency check via `suggest_slot`).
- `tbcc/docs/TEST_MAP.md` — row widened to cover both test files and the new router.
- `tbcc/extension/tbcc-context-menu-items.js` — new `tbccLoadApiSlotSelection` descriptor (`menuFamily: "media"`, `contexts: ["selection"]`, same shape as its neighbor).
- `tbcc/extension/background.js` — `tbccLoadApiSlotFromSelection()` + click-handler wiring.
- `tbcc/extension/manifest.json` — version bump.

## Design notes / judgment calls (within ceiling)

- **"Clipboard" menu actually reads `info.selectionText`**, same mechanism as `tbccCaptureSecretSelection` — a background script can't read the OS clipboard without an active-tab content-script round trip, and the existing capture-secret flow never did that either. Kept the operator's literal menu title ("Load API from clipboard") since that's the copy they specified, but the actual trigger is "select the text, then right-click," identical to the sibling menu item. Flagging this instead of silently renaming it, since the directive's wording assumes real clipboard access.
- **Fallback threshold:** the extension handler falls back to the plain key-capture picker on HTTP 400 *or* 422, not just 422 as literally written in the constraints. The register route only ever returns 400 for a bad value (`extension_capture_secret.py`'s equivalent route uses 422 for a different failure — missing key guess). Covering both status codes means the fallback fires whenever auto-registration can't cleanly happen, which is what "fall back to existing capture-secret prompt flow" is actually for.
- **`call_slot_route` never raises on a registry-level "not found"** — it forwards whatever `call_slot()` returns (`{"ok": false, "error": ...}`) with HTTP 200, same as the CLI's philosophy of "never crash the caller, report the failure in the payload." Only routing-level problems (`get_slot`/`delete` on a truly nonexistent id) use HTTP 404. Documented in a test (`test_call_route_slot_not_found_is_structured_not_http_error`) so this isn't mistaken for a bug later.

## Verification

```
cd tbcc/backend
py -3.13 -m pytest tests/test_api_slot_registry.py tests/test_tools_slots_api.py tests/test_tbcc_env_secret_store.py -x -q --tb=short
45 passed in 4.34s
```

Extension JS regression (node, from repo root):
```
node tbcc/extension/tests/tbcc-context-menu-plan.test.mjs    # ok — new item passes the dup-id/menuFamily/contexts guard
node tbcc/extension/tests/tbcc-snippet-lib.test.mjs           # ok
node tbcc/extension/tests/tbcc-download-router.test.mjs       # ok
node tbcc/extension/tests/tbcc-zip-naming.test.mjs            # ok
node --check tbcc/extension/background.js                     # syntax ok
node --check tbcc/extension/tbcc-context-menu-items.js        # syntax ok
```

**Not run:** the manual extension smoke checklist from the directive (reload extension, select key on a real page, confirm the `slot <id> ready` toast, `slots show` from CLI). This sandbox has no browser session and no outbound network (confirmed in the Phase 1 report) — the operator needs to run that checklist by hand. Steps, verbatim from the directive:

1. Reload the TBCC extension (manifest **1.40.49**).
2. On an API docs page, select the key (and base URL, if on its own line) → right-click **TBCC: Load API from clipboard**.
3. Expect toast `slot <id> ready` — not `slot api ready` (that was the pre-fix bug for `api.<vendor>.tld` hosts).
4. `py -3.13 scripts/tbcc_cli.py slots show <id> --json` should list the slot the extension just registered.

## Risks / known rough edges

1. **`backup_credential_manager` is real `cmdkey` on Windows** (`os.name == "nt"`) — every test that exercises the register route stubs it out at the `tools_slots` module level specifically so pytest never writes to the operator's actual Windows Credential Manager. If a future test imports `tools_slots.register_slot`'s dependencies differently (e.g. monkeypatching `tbcc_env_secret_store.backup_credential_manager` instead of `tools_slots.backup_credential_manager`), it will silently stop being stubbed — flagging this because the failure mode (a real CredMan write during CI) is invisible until someone inspects Windows Credential Manager by hand.
2. **Manual extension smoke unverified** (see above) — this is a "say so explicitly" case per the operating instructions, not a claim of full success.
3. **Scope: 9 files touched this phase** (`main.py`, `api_slot_registry.py`, 2 test files, `TEST_MAP.md`, `manifest.json`, `background.js`, `tbcc-context-menu-items.js`, plus the new `tools_slots.py`) — one over the CLAUDE.md 8-file scope-halt gate. Flagging per that gate rather than silently proceeding; did not halt mid-phase because every file is named explicitly in the directive's own Scope section (not sprawl), and the phase's own STOP-for-ACK gate below means nothing further happens without your sign-off regardless.

## Deferred (per phased scope — not started)

- **Phase 3:** LLM-category bridge to `llm_model_index.set_credential()`.
- Everything from the Phase 1 report's out-of-scope list still applies (island deploy/sync, per-vendor SDK codegen, MCP registration, payment/loot doctrine).

## Next steps

| What | Unblocks | Reversibility | Evidence |
|------|----------|----------------|----------|
| Run the manual extension smoke checklist above on a machine with a browser + internet | self (closes Risk 2) | trivial-revert | toast reads `slot <id> ready`; `slots show <id> --json` confirms |
| ACK this report, then proceed to Phase 3 (LLM bridge) — or stop here if Phase 0 is "done enough" | deploy (extension ships to operator browser) | trivial-revert | `/cc-report` ACK in Cursor |
| Push `0adc19b` + this phase's commit (branch `lane-c/gatekeeper-lane-split`) — still pending your confirmation from Phase 1 | other-work / deploy | trivial-revert (pre-merge branch) | `git log --oneline -3` on remote after push |

Orthogonal to `tbcc/docs/SPRINT_STATE.md`'s current goal — same as Phase 1, API Pocket is a new operator-tooling vertical, not a continuation of the sprint's tracked work.
