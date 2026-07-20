# Zeus CI/CD prep (2026-07-14)

**Status:** prep only — no live bot spawn, no monolith rewrite.

**Sources read:** `tbcc/docs/ZEUS_MENU.md`, `tbcc/backend/bots/zeus_menu.py`, `tests/test_zeus_menu.py`, Cloud Agent primer V13.

---

## 1. Honest current state

| Layer | Reality |
|-------|---------|
| **Phase 1 (shipped)** | Hub IA on `@aof_secretary_bot`: **Network \| Inbox \| Ops \| More**. `zeus:*` callbacks normalize → existing `sec:menu:*` handlers in `secretary_bot.py`. `/stack` is **display-only** from tray-backed stack status. |
| **Tests** | `tests/test_zeus_menu.py` covers normalize aliases, payment/loot username isolation, stack HTML. Mapped in `TEST_MAP.md`. |
| **North star (not shipped)** | Zeus as ops/control **monolith** — macro search merge, inline `@secretary`, content/commerce triggers (phases 2–4 in `ZEUS_MENU.md`). That is **not** Phase 1 and must not be force-fed into one PR. |
| **Gap** | No dedicated HTTP “Zeus control plane” yet; Cursor/agents reach ops via backend APIs + secretary handlers, not a Zeus-named surface. |

**Verdict:** Phase 1 menu is production-usable; monolith is a multi-phase north star. Next code should stay behind an inert API/docs boundary until CI gates exist.

---

## 2. Process boundary (hard)

| Rule | Detail |
|------|--------|
| **One writer** | Tray owns OS processes on Windows. Never `POST /bots/runtime/*/start` or spawn `payment`/`loot`/`secretary` from a second terminal if tray tabs exist → Telegram **409**. |
| **Payment stays checkout** | Stars/checkout remain on **payment** bot token (`payment_bot_username()` guard). Zeus/secretary only deep-links. |
| **Cursor → HTTP/MCP → Zeus** | Agents call backend ops endpoints / dashboard / stack-cli semantics. **Never** open raw `admin.session` from Cursor for Zeus work. Telethon stays under tray import lock / Celery. |
| **No restarts in Zeus** | Restarts = tray or `tbcc/scripts/tbcc-stack-cli.ps1` only (`ZEUS_MENU.md`). |

---

## 3. Proposed CI/CD gates (Zeus vertical)

Add / enforce before any Zeus Phase-2 code merges:

| Gate | Command / check | Fail if |
|------|-----------------|---------|
| **Lint** | existing ruff/eslint on touched files | new errors |
| **Unit smoke** | `pytest tbcc/backend/tests/test_zeus_menu.py -q` | any fail |
| **No duplicate spawn** | CI must **not** start bots; job comments cite tray ownership | start/stop process in CI |
| **Stack truth (local/operator)** | `tbcc-stack-cli.ps1 -Action Status` or `GET /ops/stack-status` | agents invent process state |
| **Callback contract** | tests assert `zeus:*` ↔ `sec:menu:*` map stays stable | silent IA break |
| **Payment isolation** | keep `test_payment_username_avoids_secretary_collision` | checkout on secretary token |

Optional later: map file entry under `docs/CI_MERGE_GATES.md` row “Zeus phase N” once API scaffold lands.

---

## 4. Next implement slice (skeleton only — not done here)

**Safe next PR (when picked):** inert FastAPI router stub, e.g. `GET /zeus/health` + `GET /zeus/menu-contract` returning the Phase-1 callback map as JSON — **no** Telegram client, **no** process control, **no** Telethon.

**Out of scope next:** merging macro search into secretary process, inline mode, commerce triggers, tray process APIs under Zeus.

**Lane for implement:** Desktop Auto · Auto (small scaffold + `test_zeus_menu` still green). Escalate only if Phase-2 IA redesign needs Plan/Ask.

---

## Operator checklist (when implementing)

1. Patch `ZEUS_MENU.md` with new endpoints.
2. Add pytest for contract JSON.
3. Confirm tray status; do not restart secretary from agent.
4. Keep payment deep-links unchanged.
