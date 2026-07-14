# Zeus monolith — architecture (Phase 0)

**Status:** Design only. No bots merged, no processes spawned by this document.
**Last updated:** 2026-07-14 (reconciled with second-opinion review — see §10 + `ZEUS_MONOLITH_REVIEW.md`)
**Companion to:** `ZEUS_MENU.md` (Phase 1, shipped), `handoffs/zeus-monolith-primer.md` (agent primer),
`handoffs/supervisor-remote-deploy-design.md` (single-writer lease).

---

## 1. North star and what is actually true today

**Zeus** = TBCC's long-term goal to consolidate the AOF Telegram surface (scattered `python -m bots.*`
processes + backend Telethon jobs) into one orchestrated control plane. Goals, in priority order:

1. **Fewer parallel processes** on the home PC (CPU / RAM / session-lock pressure).
2. **One logical API** over everything Telethon can do plus the synergies between today's bots, callable
   by operators and (later) the Cursor control plane.
3. **Payment stays the storefront.** Stars/checkout and public payment UX remain on the payment bot token
   (`@aofsubscriptions_bot` / configured). Zeus orchestrates; it does not take over checkout identity.

**What exists (do not reinvent):**

| Artifact | Reality |
|----------|---------|
| `backend/bots/zeus_menu.py` | **Phase 1 only** — secretary hub IA (Network \| Inbox \| Ops \| More); `zeus:` callbacks alias to `sec:menu:`. |
| `backend/bots/secretary_bot.py` | Hosts `/menu`, `/stack`, `on_menu_callback` — the actual handler Zeus skins. |
| `backend/app/services/telethon_session_lock.py` | **Single-writer already exists** at the session-file / MTProto layer (Redis account lock). |
| `docs/ZEUS_MENU.md` | Phase 1 docs; later phases sketched, **not shipped**. |
| Tray (`scripts/tbcc-service-control.ps1`) | Every bot is a separate process today (ids below). |

**Not true yet:** "Zeus = all bots merged" or "Cursor has live Telegram everywhere." Phase 1 is a menu skin,
not a monolith.

---

## 2. Capability matrix

Rows = every consolidation candidate. **Transport** = Bot API (own bot token, `getUpdates` long-poll) vs
Telethon (MTProto on `admin.session`). **Session risk** is the inherent contention class (see §3 for why
Bot-API merges are *not* inherently 409-risky). **Transport for every row was confirmed from source in the
2026-07-14 second-opinion pass** (`ZEUS_MONOLITH_REVIEW.md`); the former `(verify)` cells are now resolved.

### 2a. Bot-API bots (own token, long-poll)

| Capability | Current module | Target Zeus module | Merge phase | Session/409 risk |
|------------|----------------|--------------------|-------------|------------------|
| Secretary hub (Zeus host) | `bots/secretary_bot.py` + `bots/zeus_menu.py` | stays host; extract handlers → `zeus_core` | 1 | None (own token) |
| Payment / checkout | `bots/payment_bot.py`, `bots/payment_pipeline.py`, `bots/subscription_bot.py` | **token unchanged**; logic → shared `zeus_core.payment` | 5 (last) | Token-level only, migration-transient |
| Loot room | `bots/loot_bot.py` | `zeus_core.loot` (URL button in menu today) | 4 | Token-level only |
| Companion | `bots/companion_bot.py` | `zeus_core.companion` (URL button today) | 4 | Token-level only |
| Macro search | `bots/macro_search_bot.py` (+ `_forum`, `_telegram`) | into secretary process (ZEUS_MENU Phase 2) | 2 | Token-level only |
| LLM chat | `bots/llm_chat_bot.py` | `zeus_core.chat` (default-off in lean) | 4 | Token-level only |
| Storage-hub deposit | `bots/storage_hub_deposit_bot.py`, `bots/secretary_storage_deposit.py` | `zeus_core.storage` | 3 | Token-level only |
| Album composer / Remixer | `bots/album_composer_bot.py` | keep as worker face; ops via Zeus router | 3 | **Token-level** — Bot-API poller (`run_polling`); emoji upload is HTTP → Celery (Telethon runs server-side, not in the bot process) |
| Scraper control | `bots/scraper_bot.py` | Zeus router trigger | 3 | See scrape row below |

### 2b. Backend Telethon jobs (MTProto on `admin.session` — inherent single-writer)

| Capability | Current module(s) | Target | Merge phase | Session/409 risk |
|------------|-------------------|--------|-------------|------------------|
| Scrape | `services/scraper_telethon_auth.py`, `bots/scraper_bot.py` | Zeus trigger → existing Celery job | 3 | **High** — MTProto on `admin.session`; must hold Redis account lock |
| Relay ("now playing") | `services/listening_relay_*.py` → Celery poster (`poster_worker.py`) | Zeus trigger → existing Celery job | 3 | **High** — Telethon poster on the poster session; must hold Redis account lock |
| Emoji packs | `services/emoji_pack_telethon.py`, `emoji_factory_async.py`, `telegram_custom_emoji.py` | Zeus write endpoint (upload pack) | 4 | **High** — custom-emoji upload needs user account / MTProto |
| Dividers | `post_divider_storage.py` (disk), `main_channel_post_divider.py` (send) | Zeus trigger | 3 | Storage: **none** (filesystem). Send: **High** — Telethon |
| Growth | `aof_growth_hub.py`, `growth_promo.py`, `growth_reaction.py`, `growth_attribution.py` | Zeus trigger / read | 3 | Mixed — `growth_reaction.py` is **observe-only** (none); any other growth path posting via `admin.session` is **High** |
| **Admin userbot** | `bots/admin_bot.py` | **redesign — do NOT fold into secretary** | deferred | **High** — long-lived Telethon userbot (`TelegramClient` + `run_until_disconnected`) |

**Reading the risk column:** a row is dangerous to merge only if it holds a live MTProto connection on the
shared `admin.session`. Bot-API rows are safe to co-host — they each keep their own token.

---

## 3. Why "409 risk" splits into two very different things

Two failure modes get conflated as "duplicate bot":

- **Token-level (Bot API) — 409 Conflict.** Telegram returns 409 when two processes call `getUpdates` on the
  **same bot token**. Merging Bot-API bots into one process does **not** create this — each bot keeps its own
  token and its own single long-poll. The only 409 window is *transient*: a duplicate old process still
  polling during a migration cutover. Mitigation is operational (tray stop-old-before-start-new), not
  architectural. **This is why the payment token must never move: identity == token.**

- **Session-level (Telethon) — MTProto contention.** Copied session files derived from `admin.session`
  share one Telegram auth key; only one live MTProto connection is allowed. Concurrent connections cause
  "wrong session ID" / "very old message" / `database is locked` storms. This is **inherent** and already
  guarded — see §5.

Design consequence: consolidating Bot-API bots is a **process-count win with low *Telegram* risk — but
medium host/bootstrap risk.** Every bot today is a blocking `run_polling()` that owns its process event loop,
so co-hosting needs a new multi-`Application` runner (init / start / coordinated shutdown for N apps on one
loop, shared signal handlers) that does not exist in-repo yet. Treat Phase 2 as *"prove the multi-app host,"*
not *"move files and flip the tray."* Consolidating Telethon jobs is **where the single-writer invariant
actually bites**.

---

## 4. Process target — what disappears vs stays

Tray service ids today (`scripts/tbcc-service-control.ps1`): `backend, dashboard, forum, celery,
celery_post, celery_post_scheduler, celery_ops, beat, payment, secretary, companion, admin, macro_search,
loot, album_composer, openclaw, llm_chat, watch, nsfw, lustpress, clip`.

| Service id | Fate under Zeus | Why |
|------------|-----------------|-----|
| `secretary` | **Stays — becomes Zeus host process** | Already the menu host; `zeus_core` co-hosts merged Bot-API handlers here. |
| `payment` | **Stays (token face)** | Checkout identity must remain its own token; logic may share `zeus_core`, process stays. |
| `macro_search`, `llm_chat` | **Merge into secretary/Zeus** | Bot-API only — process-count win, behind a multi-`Application` host. |
| `admin` | **Redesign — NOT a Bot-API merge** | Long-lived Telethon userbot on a shared session; folding into secretary is a session-risk merge, not a token co-host. Deferred. |
| `companion`, `loot` | **Candidate merge (later)** | Bot-API; keep as URL faces until Phase 4 co-host is proven. |
| `album_composer` | **Stays (worker face)** | Marked mandatory in tray; ops exposed via Zeus router, process unchanged. |
| `backend`, `celery*`, `beat` | **Stay** | Infra; Telethon jobs already run here behind Celery + the account lock — Zeus *routes* to them, does not re-host. |
| `dashboard, forum, openclaw, watch, nsfw, lustpress, clip` | **Out of scope** | Not part of the Telegram surface. |

Net target: collapse `macro_search` + `llm_chat` (and eventually `companion`, `loot`) into the `secretary`/Zeus
process behind a multi-`Application` host. **Payment and album_composer keep their process identity; `admin` is
a Telethon userbot and is *not* part of the Bot-API merge.** No Telethon job process is added or removed —
Zeus is a router in front of the existing Celery lane.

---

## 5. Session strategy — two layers (different scopes)

These are **different scopes, not a choice.** Layer A guards live MTProto connections; Layer B guards who may
issue a process **Start**. Only an **agent/remote Start path** needs both — read-only Zeus HTTP (Phases 0–3a)
needs neither Layer B nor an `owner.lock`.

**Layer A — runtime session serialization (exists today).**
`services/telethon_session_lock.py` — Redis locks per session file (`admin`, `import`, `poster`) nested under
a global `TBCC_TELEGRAM_ACCOUNT_LOCK` account lock. This serializes concurrent MTProto access *across
processes* (uvicorn + Celery workers) so only one live connection uses the shared auth key at a time. Any Zeus
endpoint that fans out to a Telethon job inherits this for free — it must not bypass it.

**Layer B — process-lifecycle ownership (proposed, `supervisor-remote-deploy-design.md`).**
A single `.tbcc-run/owner.lock` (`{host, pid, acquiredAt}`) that any actor — local tray or remote/agent —
must hold to issue a **Start**. The tray is the natural default lease-holder. This governs *who may launch a
process*, before Layer A ever comes into play. No silent takeover: a remote Start either finds the lease free
and acquires it, or hard-fails with "local tray holds control." **Not required for read-only Zeus phases** —
implement only when an agent/remote `Start` path is actually built (Phase 3b/4+).

**Bot tokens & identities:**
- `payment` bot token = storefront identity, **immovable**.
- `secretary` bot token = Zeus host / admin surface.
- **Dedicated agent bot (future):** agents get a *separate* bot token for Zeus write calls — never raw
  `admin.session` from an agent terminal, and never the payment token.

Rule: **agents call Zeus HTTP/MCP → tray-owned single writer.** Never a second `python -m bots.*` and never
raw session access from an agent shell.

---

## 6. Control plane sketch — `POST /zeus/v1/...`

On the existing FastAPI (`:8000`, already serves `/ops/*`, `/health/*`). **Read-first, write-behind-lease.**
The headline read route is a thin alias: `GET /ops/stack-status` already ships (`app/api/ops_stack.py` →
`tbcc_stack_control.get_stack_status`), so `GET /zeus/v1/stack/status` is a namespace facade, not new logic.

**Allowed (agent-safe, read):**
| Route | Maps to |
|-------|---------|
| `GET /zeus/v1/stack/status` | `tbcc-stack-cli.ps1 -Action Status` shape (panel already parses it) |
| `GET /zeus/v1/health` | existing `/health/*` |
| `GET /zeus/v1/hub/tail` | copy-hub tail (read) |
| `GET /zeus/v1/inbox/summary` | secretary inbox status (read) |

**Allowed (agent-safe, write — narrow, idempotent, behind allowlist + lease):**
| Route | Maps to | Guard |
|-------|---------|-------|
| `POST /zeus/v1/storage/deposit` | `services/storage_topic_deposit.py` | allowlist + rate limit |
| `POST /zeus/v1/emoji/pack` | `emoji_pack_telethon.py` | Layer A account lock (High-risk row) |
| `POST /zeus/v1/relay/trigger` | listening-relay job | Layer A if Telethon poster |

**Forbidden from agents (operator-only):**
- Any bot `Start` / `Stop` / `Restart` (Layer B lease + operator gate).
- Blind "Start all bots" / stack launch.
- Raw `admin.session` access; issuing the payment token.

Restarts stay tray-only through every phase unless the operator explicitly changes that (Phase-1 rule
preserved).

---

## 7. Cursor agent allowlist (once Phase 3 exists)

Agents may call **only** the read routes in §6 plus the narrow, idempotent writes explicitly listed there,
using the **dedicated agent bot token**, over Zeus HTTP/MCP. Everything else — process lifecycle, payment
identity, raw sessions — is operator-only. This list is the contract; widening it is an operator decision.

---

## 8. Phased roadmap

| Phase | Goal | Verify |
|-------|------|--------|
| **0** | This doc: matrix, process target, control-plane sketch, session strategy, roadmap. | File exists; `pytest tests/test_zeus_menu.py` green **modulo the one known pre-existing loot deep-link assertion** (unrelated to Zeus). |
| **1** | `zeus_core` library **+ multi-`Application` host proof** (secretary + one low-traffic Bot-API token on one loop). Not file moves alone. | **Host proof shipped 2026-07-14** — `bots/zeus_multi_app.py` + gated `bots/zeus_cohost_spike.py` (secretary+llm_chat); `tests/test_zeus_multi_app.py`. Not tray-wired. |
| **2** | Tray-merge that one Bot-API token into the host. **`admin` excluded — it is Telethon.** | One fewer tray service; menu still works; tray CommandMatch updated. |
| **3a** | **Read-only** `/zeus/v1` facade aliasing existing `/ops/*` + health. No write, no Telethon, no lease. | **Shipped 2026-07-14** — `GET /zeus/v1/stack/status` == `/ops/stack-status`; `tests/test_zeus_v1.py`. |
| **3b** | Telethon *triggers* (scrape / relay / emoji) behind Layer A. | Job runs with the Redis account lock held; no second `admin.session` connect. |
| **4** | Agent-safe **write** endpoints (storage deposit, emoji pack) behind allowlist + Layer B lease. | Operator smoke; lock held; `companion`/`loot` co-host trial. |
| **5** | Payment **logic** shared via `zeus_core`; payment **bot token unchanged**. | Checkout regression checklist; token identity unchanged. |

**Phase-1-menu invariant:** the shipped Zeus menu (`zeus:` → `sec:menu:`) must keep working through every
phase.

**Recommended build order (per second opinion):** **3a** read-only facade (cheapest, freezes the agent
allowlist contract, zero session risk) → **1** `zeus_core` extract *with* the multi-`Application` host proof →
**2** tray-merge one low-traffic token → **3b/4** Telethon triggers + writes behind Layer A/B → **5** payment
logic. The `admin` userbot merge is deferred pending a session-safe redesign.

---

## 9. Concrete follow-ups (next slices)

1. ~~Confirm transport for the `(verify)` rows~~ — **done (2026-07-14 review):** relay = High Telethon poster;
   divider storage = none / send = High; `growth_reaction` = observe-only; album_composer = Bot-API poller +
   server-side Celery upload; **`admin` reclassified as High Telethon userbot.**
2. **Phase 1 `zeus_core` extract plan:** enumerate the exact `on_menu_callback` handlers in
   `secretary_bot.py` to lift, with test coverage each.
3. **Define the `.tbcc-run/owner.lock` schema + acquire/release flow** (Layer B) before any Zeus write route.
4. ~~Read-only router spike~~ — **done (2026-07-14):** `GET /zeus/v1/stack/status` aliases
   `build_stack_status_payload()` / `/ops/stack-status` (`app/api/zeus_v1.py`, `tests/test_zeus_v1.py`).
5. **Dedicated agent bot token provisioning** + allowlist enforcement middleware for §6/§7.

**Stop condition (Phase 0):** this doc + `test_zeus_menu.py` green. Do not merge bots or spawn processes.

---

## 10. Second opinion — reconciled 2026-07-14

Independent review: **`docs/ZEUS_MONOLITH_REVIEW.md`**. The corrections below are **now folded into §§2–9
above** and each was re-verified against source before applying:

- **`admin_bot` is Telethon (High), not Bot-API** — moved to §2b; removed from the Phase-2 secretary merge.
  *Verified:* `admin_bot.py` L7 `from telethon import TelegramClient`, L91 client, L519 `run_until_disconnected`.
- **Layer B ≠ Layer A** — §5 now scopes `owner.lock` to agent/remote Start paths only (not read-only HTTP).
- **Bot-API co-host is low *Telegram* risk, medium host risk** — §3 now flags the missing multi-`Application`
  runner (every bot is a blocking `run_polling()` today).
- **`(verify)` rows resolved** in §2b: relay = Telethon poster (High); divider storage = none / send = High;
  `growth_reaction` = observe-only; album_composer = Bot-API poller + server-side Celery upload.
- **Read-only facade is a real alias** — §6 now cites the shipping `app/api/ops_stack.py` → `/ops/stack-status`.

**Recommended next slice (adopted into §8 build order):** the thin read-only `/zeus/v1` facade over existing
`/ops/stack-status` — cheapest, zero session risk, freezes the agent allowlist — *before* the `zeus_core`
extract + multi-`Application` co-host spike. Do **not** merge `admin_bot`, implement `owner.lock`, or add
Telethon write triggers until the facade + co-host spike land.
