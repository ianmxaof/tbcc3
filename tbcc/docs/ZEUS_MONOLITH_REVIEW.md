# Zeus monolith — Phase 0 second opinion (2026-07-14)

**Status:** Review only. No product code, no merges, no process starts.
**Artifact reviewed:** `tbcc/docs/ZEUS_MONOLITH.md` (Phase 0)
**Sources:** primer, `ZEUS_MENU.md`, `zeus_menu.py` / `secretary_bot.py`, `telethon_session_lock.py`,
`supervisor-remote-deploy-design.md`, `tbcc-service-control.ps1`, and the `(verify)` modules named below.

**pytest:** `tests/test_zeus_menu.py` → **9 passed, 1 failed**
(`test_network_submenu_has_url_deep_links` still expects `t.me/lootbot?start=loot_free`; loot CTA is now
`telegram.me/{loot}` without `?start=` — pre-existing, unrelated to Zeus. No new failures from this review.)

---

## Verdicts A–E

### A. Session strategy — is Layer B redundant?

**Verdict: scopes are different; Layer B is not redundant with Layer A — but it is premature for Zeus Phases 0–3.**

| Layer | What it serializes | Evidence |
|-------|--------------------|----------|
| **A** | Live **MTProto connections** across uvicorn/Celery (and any other process that opens a Telethon client on a shared auth key) | `telethon_session_lock.py` L1–11, L65–84: Redis per-session keys + nested `TBCC_TELEGRAM_ACCOUNT_LOCK` |
| **B** | Who may issue **process Start** (tray vs remote/agent) | `supervisor-remote-deploy-design.md` L9–14: `.tbcc-run/owner.lock` before any Start |

Layer A does **not** stop a second actor from launching `python -m bots.payment_bot` (token-level 409) or a second long-lived Telethon listener. Layer B does **not** serialize concurrent Celery poster + scrape once both processes are already up.

**Exact race Layer B covers that Layer A does not:** remote/agent `Start` while the local tray already owns (or is mid-start of) the same service — silent double-spawn → Bot-API 409 and/or a second Telethon connect that then fights Layer A (or races before the lock is acquired).

**Correction for the doc:** call Layer B **required before any agent/remote Start path**, not “required for Zeus” in general. Phases 0–3 (read-only HTTP, no Start) do not need `owner.lock` implemented yet. Do not invent Layer B as a substitute for Layer A on Telethon rows.

---

### B. “Bot-API merges are low-risk” — does it hold?

**Verdict: token-level 409 math is correct; “cheap co-host” understates PTB reality. Co-hosting is medium engineering risk, low Telegram risk.**

What the doc gets right (`ZEUS_MONOLITH.md` §3):
- 409 is **per bot token**. Distinct tokens in one process do not inherently 409.
- Payment identity = payment token must stay put.

What it underplays:
1. **Every Bot-API entrypoint today is a single blocking `run_polling()`** — secretary L2630, payment L2390, loot L1116, companion L1235, macro_search L226, llm_chat L192, album_composer L3402. That API owns the process event loop. Co-hosting requires a **new multi-Application runner** (`initialize` / `start` / `updater.start_polling` for N apps on one loop, coordinated shutdown, shared signal handlers). None of that exists in-repo.
2. **Hidden coupling is operational, not Telegram:** shared `bots/__init__` env load, DB session patterns, error reporters, `create_task` fire-and-forget (loot L1005, album_composer L1439), bootstrap retries, and tray **CommandMatch** strings that assume one process per module (`tbcc-service-control.ps1` L953–998).
3. **Handler isolation is fine across separate `Application` instances** (no shared handler table) — but callback/command namespaces and operator muscle memory still matter during cutover.

**Bottom line:** Bot-API merge is low *Telegram* risk and **non-trivial process/bootstrap risk**. Treat Phase 2 as “prove multi-app host,” not “move files and flip tray.”

---

### C. Next slice — Phase 1 (`zeus_core`) vs Phase 3 (read-only router)?

**Verdict: do Phase 3 first — but as a thin facade over existing ops, not a greenfield control plane. Then redefine Phase 1 as extract + multi-app host scaffold before any tray merge.**

Reasons:
1. **`GET /ops/stack-status` already exists** (`app/api/ops_stack.py` L12–23 → `get_stack_status`). Phase 3’s headline route is largely a namespace alias (`/zeus/v1/stack/status` → same shape). Zero write surface, zero session risk, locks the agent allowlist contract early.
2. **Pure `zeus_core` extract without a co-host runner does not de-risk the monolith.** It rearranges secretary handlers (`on_menu_callback` at `secretary_bot.py` L1777+) but never exercises the hard assumption in B.
3. Sequencing that best de-risks: **3a read facade → 1 = library + multi-Application host proof (secretary + one low-traffic Bot-API token) → 2 = tray merge of that token → Telethon triggers later behind Layer A.**

Do **not** implement Telethon *trigger* writes in the first Phase 3 spike (doc §8 Phase 3 currently mixes “read-only” with “Telethon triggers” — split those).

---

### D. `(verify)` matrix rows — actual transport

| Row | Doc claim | Actual transport | Session-risk class | Cite |
|-----|-----------|------------------|--------------------|------|
| **Relay** | (verify) Bot API vs poster session | **Telethon poster** via Celery → `post_listening_relay_message` → `TelegramClient` + poster session lock | **High** | `listening_relay_worker.py` L12; `listening_relay_send.py` L12, L172–216; `poster_worker.py` L259–318, L783+ |
| **Dividers** | (verify) via `post_divider_storage.py` | **Storage is disk-only** (no Telegram). **Send path is Telethon** in `main_channel_post_divider.py` | Storage: none. Post: **High** | `post_divider_storage.py` L1–47 (filesystem); `main_channel_post_divider.py` L12, L162 |
| **Growth reactions** | (verify) reaction/post via admin.session | **`growth_reaction.py` is observe-only** — Redis proposals, “Nothing here posts to Telegram” | **None** (this module). Other growth post paths may still be High — do not conflate | `growth_reaction.py` L1–10, L79–80 |
| **Album composer** | Token-level; (verify) admin.session | **Bot-API poller** (`Application.builder` + `run_polling`). Emoji upload is **HTTP → backend/Celery** (Telethon happens server-side, not in the bot process) | Bot process: **token-level**. Upload job: **High** (Celery + Layer A) | `album_composer_bot.py` L3365–3402, L3090–3121, L2930 |
| **Admin (extra — matrix error)** | Listed under Bot-API, “Token-level only,” merge Phase 2 | **Long-lived Telethon userbot** on admin-derived session | **High** — must **not** fold into secretary Bot-API merge | `admin_bot.py` L7, L55–91, L504–527 |
| **Scraper “bot”** | Split across Bot-API control + Telethon scrape | `bots/scraper_bot.py` is **Telethon scrape code**, not a PTB Application | **High** | `scraper_bot.py` L6–7, L410–425 |

---

### E. What the doc gets wrong or omits

1. **`admin` is misclassified as Bot-API / low-risk Phase 2 merge.** It is a permanent MTProto listener (`TelegramClient` + `run_until_disconnected`). Folding it into secretary is a **session-risk merge**, not a token co-host. Process-target table L103 is wrong for the same reason.
2. **Phase 3 verify is too weak / blurred.** `curl /zeus/v1/stack/status` is fine for a facade — but “Telethon *triggers* behind Layer A” is a write surface and needs lock-held assertions + no second `admin.session` connect. Split read Phase 3a from trigger Phase 3b/4.
3. **`GET /ops/stack-status` already ships** — doc §6 should cite it as the implementation seed so Phase 3 is not over-scoped.
4. **Layer B timing overstated** (§5 “both required” for any remote/agent Start is right; implying both for early Zeus phases is not).
5. **ZEUS_MENU.md “later phases” numbering conflicts** with monolith phases (menu Phase 2 = macro merge; monolith Phase 2 = same idea but admin is wrongly included). Align names.
6. **Co-host cutover omission:** tray must stop old process before starting merged host; CommandMatch / service ids for disappeared bots; lean-stack filters. Mention in Phase 2 verify.
7. **Payment “logic → zeus_core” (Phase 5)** is fine; keep stressing **no token move** and **no co-host of payment poller into secretary until checkout regression is defined** — process-target already keeps `payment` separate (good).
8. **Phase 0 verify line** (“`test_zeus_menu.py` green”) is currently **false** on this tree (1 pre-existing loot CTA failure). Say “green modulo known loot deep-link assertion” or update the test in a non-Zeus PR.

---

## Concrete corrections to apply to `ZEUS_MONOLITH.md`

1. Move **`admin`** from §2a Bot-API to §2b Telethon; session risk **High**; merge phase **deferred / redesign** (not Phase 2 with macro_search).
2. Resolve `(verify)` cells per table D (relay High Telethon; divider storage none / send High; growth_reaction none; album_composer token + async High upload).
3. Soften §3 “low intrinsic risk” → “low Telegram risk; medium host/bootstrap risk — requires multi-Application runner.”
4. §5: Layer B required **before agent/remote Start**, not before read-only Zeus HTTP.
5. §6/§8: Phase 3 = read facade over `/ops/*` first; Telethon triggers = later phase with Layer A proof.
6. §4 process table: remove `admin` from “Merge into secretary/Zeus” Bot-API bucket.
7. §9 follow-up 1 can be marked **done** for the four `(verify)` rows (this review).

---

## Single recommended next slice

**Build a read-only `/zeus/v1` facade** on FastAPI that aliases at least `GET /zeus/v1/stack/status` (and optionally health/hub tail) to the existing `/ops/stack-status` / health helpers — no Start, no Telethon, no Layer B, no bot merges. Ship with a tiny pytest on response shape.

**Why this over pure `zeus_core` extract:** it costs almost nothing, freezes the agent allowlist contract, and avoids a speculative secretary refactor before the multi-Application host pattern is proven. **Immediately after** that facade, the next *hard* slice should be a **co-host spike** (secretary Application + one low-traffic Bot-API bot on one loop) — that is the real Phase 1 for a monolith, not file moves alone.

**Do not:** merge `admin_bot`, implement `owner.lock`, or add Telethon write triggers until the facade + co-host spike land.

---

## Operator smoke (Tray only — after a future implement phase)

Not required for this doc/review. When the facade ships: `curl` localhost `:8000/zeus/v1/stack/status` and compare to tray Status / existing `/ops/stack-status`. No bot Start from agents.
