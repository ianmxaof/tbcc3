# Zeus monolith — dedicated agent primer

**Use:** Paste the fenced block below into a **new Cursor chat** titled something like `Zeus monolith`. Zero prior context assumed.

**Last synced:** 2026-07-14  
**Branch default:** `feat/zeus-monolith` (create if missing)  
**Repo root:** `C:\Powercore-repo-main\telegram_bot2` (TBCC under `tbcc/`)

---

## Paste block (start here)

```text
# Zeus monolith — fresh agent thread

You are the dedicated agent for **Zeus**: TBCC's long-term goal to consolidate AOF Telegram bot + Telethon capability into one orchestrated surface, cutting process count and CPU while giving operators (and future Cursor control plane) a single API.

## North star (operator intent)

- **Zeus API** = one logical control plane over everything Telethon can do + every synergy between today's scattered bots.
- **Fat trim:** fewer parallel `python -m bots.*` processes on the home PC (payment, loot, secretary, album_composer, companion, macro_search, …).
- **Payment bot stays the storefront:** Stars/checkout and public payment UX remain on `@aofsubscriptions_bot` (or configured payment token). Zeus orchestrates; it does not replace checkout identity on day one.
- **Cursor/agent access (future):** agents call **Zeus HTTP/MCP** → tray-owned single writer — NOT raw `admin.session` from agent terminals (409 / lock storms).
- **Links / gate-link vertical:** paused — do not expand AOF Link Hub or gate migrations unless explicitly reopened.

## What exists today (do not reinvent)

| Artifact | Reality |
|----------|---------|
| `tbcc/backend/bots/zeus_menu.py` | **Phase 1 only** — secretary hub IA: Network \| Inbox \| Ops \| More; `zeus:` callbacks alias to `sec:menu:` |
| `tbcc/backend/bots/secretary_bot.py` | Hosts `/menu`, `/stack`, `on_menu_callback` for Zeus |
| `tbcc/docs/ZEUS_MENU.md` | Phase 1 docs; later phases listed but **not shipped** |
| `tbcc/backend/tests/test_zeus_menu.py` | Menu callbacks, stack HTML |
| `tbcc/docs/handoffs/CLOUD_AGENT_PRIMERS.md` | V13 = Zeus menu slice (narrow); this primer supersedes V13 for monolith work |
| Tray services | `payment`, `secretary`, `loot`, `album_composer`, `companion`, `macro_search` — each separate process today (`tbcc/scripts/tbcc-service-control.ps1`) |

**Not true yet:** "Zeus = all bots merged" or "Cursor has live Telegram in every chat." Phase 1 is a menu skin on secretary, not a monolith.

## Non-negotiables

1. **Never** commit `.env`, `*.session*`, tokens, `.tbcc-run/` secrets.
2. **Never** spawn duplicate Telegram bots from agent terminals while tray may be running (`POST /bots/runtime/*/start`, second `python -m bots.*`). Process truth: tray / `tbcc-stack-cli.ps1 -Action Status`.
3. **Single Telethon writer:** one session owner at a time; design interlocks before merging userbot paths.
4. **Restarts:** tray or operator — Zeus docs say restarts are not in-menu for Phase 1; monolith design must preserve that until explicitly changed.
5. Read `tbcc/docs/SPRINT_STATE.md` + `tbcc/docs/TEST_MAP.md` before substantive edits.
6. Small PRs; pytest for logic; PowerShell stays ASCII-only (WinPS 5.1).

## Recommended first slice (Phase 0 — architecture, no merge yet)

Deliver **`tbcc/docs/ZEUS_MONOLITH.md`** (or extend `ZEUS_MENU.md` with a monolith section) containing:

1. **Capability matrix** — rows: payment, loot, secretary, album_composer, companion, macro_search, backend Telethon jobs (scrape, relay, emoji, dividers, growth). Columns: Bot API vs Telethon, current module, target Zeus module, merge phase, 409 risk.
2. **Process target** — which processes disappear vs stay (payment storefront likely stays as token face even if logic shared).
3. **Control plane sketch** — `POST /zeus/v1/...` routes agents may call (post to storage topic, run stack status, upload emoji pack) vs forbidden (blind Start all bots).
4. **Session strategy** — admin.session, bot tokens, dedicated agent bot; single-writer lease pattern (see `supervisor-remote-deploy-design.md`).
5. **Phased roadmap** — numbered phases with verification each; Phase 1 menu stays working throughout.

**Do not** merge all bots in slice 0. Architecture + tests plan only unless operator explicitly says "implement Phase 1 merge."

## Later phases (sketch — adjust in doc)

| Phase | Goal | Verify |
|-------|------|--------|
| 0 | Architecture doc + matrix | File exists; ≥5 concrete follow-ups |
| 1 | Shared `zeus_core` library extracted from secretary ops handlers (no new process) | `pytest test_zeus_menu.py` + new unit tests |
| 2 | Macro search → secretary process (per ZEUS_MENU.md phase 2) | One fewer tray service when enabled |
| 3 | Zeus HTTP router on backend `:8000` (read-only ops first) | `curl` stack status; no bot Start |
| 4 | Agent-safe write endpoints (storage topic post, emoji pack) behind allowlist | Operator smoke only |
| 5 | Payment logic shared module; payment **bot token** unchanged | Checkout regression checklist |

## Key paths to read first

- `tbcc/docs/ZEUS_MENU.md`
- `tbcc/backend/bots/zeus_menu.py`
- `tbcc/backend/bots/secretary_bot.py` (search `zeus`, `on_menu_callback`, `/stack`)
- `tbcc/backend/bots/payment_bot.py` (scope only — do not merge without plan)
- `tbcc/backend/bots/album_composer_bot.py` (Remixer / storage hub posts)
- `tbcc/backend/app/services/emoji_pack_telethon.py`, `telegram_custom_emoji.py`
- `tbcc/scripts/tbcc-service-control.ps1` (service ids)
- `tbcc/docs/TBCC_PROTOCOLS.md` (tray supervisor)
- `tbcc/docs/handoffs/supervisor-remote-deploy-design.md` (single-writer)

## Verification commands

```powershell
# Parse / unit (always)
cd C:\Powercore-repo-main\telegram_bot2\tbcc\backend
pytest tests/test_zeus_menu.py -x -q

# Stack truth (operator — do not Start bots from agent)
powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\tbcc-stack-cli.ps1 -Action Status
```

## Working agreement

- Branch: `feat/zeus-monolith`
- Commit per completed phase; **do not push** unless operator asks
- End each session with: what shipped, tests, risks, next slice
- If scope exceeds architecture doc → run mental preflight: ≥3 files or backend+bots = plan first

## Task for this session

Phase 0: Read the key paths above and write `tbcc/docs/ZEUS_MONOLITH.md` with the capability matrix, control plane sketch, session strategy, and phased roadmap. Optionally add a one-page "Cursor agent allowlist" section listing which HTTP routes agents may call once Phase 3 exists.

Stop after Phase 0 doc + pytest still green. Do not merge bots or spawn processes.
```

---

## After Phase 0

Return to supervisor thread or say **"read Zeus Phase 0 doc"** in this repo. Next slice is usually shared `zeus_core` extract or Zeus HTTP read-only router — pick one phase at a time.
