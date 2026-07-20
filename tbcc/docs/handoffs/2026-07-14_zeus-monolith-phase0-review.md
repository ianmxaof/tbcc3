# Zeus monolith — Phase 0 second-opinion handoff

**Use:** Paste the fenced block below into a **new Cursor chat** titled `Zeus Phase 0 review`. This is a
**review / second-perspective** task, not an implementation ticket. The goal is to stress-test the Phase 0
architecture doc and the recommended next slice before any code is written.

**Created:** 2026-07-14
**Repo root:** `C:\Powercore-repo-main\telegram_bot2` (TBCC under `tbcc/`)
**Artifact under review:** `tbcc/docs/ZEUS_MONOLITH.md` (Phase 0, just written — untracked)
**Sibling context:** `tbcc/docs/handoffs/zeus-monolith-primer.md` (the primer that scoped Phase 0)

---

## Paste block (start here)

```text
# Zeus monolith — Phase 0 review (fresh thread, second opinion)

You are a reviewer, not an implementer. TBCC wants to consolidate its scattered AOF Telegram bots +
backend Telethon jobs into one orchestrated control plane ("Zeus"). A first agent just delivered the
Phase 0 architecture doc. Your job is to give an independent second perspective on whether that
architecture is sound and which slice to build next. **Do not write product code, merge bots, or spawn
processes.** Output is a written review only.

## Read first (in order)
1. `tbcc/docs/ZEUS_MONOLITH.md`            <- the doc under review (matrix, process target, session strategy, roadmap)
2. `tbcc/docs/handoffs/zeus-monolith-primer.md`   <- the north star / non-negotiables that scoped it
3. `tbcc/docs/ZEUS_MENU.md` + `tbcc/backend/bots/zeus_menu.py`  <- Phase 1 (shipped menu skin)
4. `tbcc/backend/bots/secretary_bot.py`   <- the real handler Zeus skins (search: zeus, on_menu_callback, /stack)
5. `tbcc/backend/app/services/telethon_session_lock.py`  <- the single-writer that ALREADY exists (Redis account lock)
6. `tbcc/docs/handoffs/supervisor-remote-deploy-design.md`  <- the proposed .tbcc-run/owner.lock file-lease
7. `tbcc/scripts/tbcc-service-control.ps1`  <- real tray service ids (grep: Id = ")

## Non-negotiables (inherited — do not challenge these, design within them)
1. NEVER commit secrets, `.env`, `*.session*`, tokens.
2. NEVER spawn Telegram bots / Celery workers, no `POST /bots/runtime/*/start`. Process ownership is the
   Windows tray only.
3. Single Telethon writer: one live MTProto connection on the shared `admin.session` auth key at a time.
4. Payment bot TOKEN is the storefront identity and must not move.
5. Restarts stay tray-only through every phase unless the operator explicitly changes that.
6. This is a doc/review task — no product code.

## What I want a second perspective on (answer each explicitly)

A. **Session strategy — is Layer B redundant?** The doc argues for TWO locks: (A) the existing Redis
   MTProto account lock in `telethon_session_lock.py`, and (B) a proposed `.tbcc-run/owner.lock`
   process-lifecycle file-lease. Are these genuinely different scopes, or is Layer B reinventing what the
   tray + Redis lock already cover? If Layer B is needed, what exact race does it prevent that Layer A
   does not?

B. **"Bot-API merges are low-risk" — does this hold in practice?** The doc claims merging Bot-API bots
   into one process is a cheap win because each keeps its own token (409 is per-token, migration-transient).
   Pressure-test that against python-telegram-bot reality: can N `Application` instances / pollers co-exist
   in one process cleanly (event loop, per-bot `getUpdates`, shared handlers, graceful shutdown)? Is there
   hidden coupling that makes co-hosting harder than the doc implies?

C. **Which slice next — Phase 1 (`zeus_core` extract) or Phase 3 (read-only HTTP router)?** The doc
   orders them 1 then 3. Argue for the sequencing that best de-risks the monolith: is it safer to extract
   shared library code first, or to prove the read-only control plane (`GET /zeus/v1/stack/status`) first
   since it has zero write surface and no session risk? Recommend one, with reasoning.

D. **The `(verify)` matrix rows.** The doc marks relay (`listening_relay_*`), dividers
   (`post_divider_storage.py`), growth reactions (`growth_reaction.py`), and album_composer as unverified
   transport (Bot API vs `admin.session`). Spot-check the source and tell me which actually hold a
   Telethon/MTProto connection — that decides their real session-risk class and merge phase.

E. **Anything the doc gets wrong or omits.** Payment-token-immovable, the process-target table, the
   `/zeus/v1` allow/forbid split, the agent allowlist — flag any claim that is incorrect, any risk the
   roadmap misses, or any phase whose verification step is too weak to catch a regression.

## Deliverable
A written review — either a new `tbcc/docs/ZEUS_MONOLITH_REVIEW.md` or a clearly-marked
"## Second opinion (2026-07-14)" section appended to `ZEUS_MONOLITH.md`. Structure it as: (1) verdict on
each question A–E, (2) concrete corrections to the doc, (3) your single recommended next slice with a
one-paragraph justification. Cite real file paths/line numbers for every claim; do not assert a module path
you have not opened.

## Verify before you finish
cd C:\Powercore-repo-main\telegram_bot2\tbcc\backend
pytest tests/test_zeus_menu.py -q
# NOTE: one test (test_network_submenu_has_url_deep_links) currently FAILS on this tree — pre-existing,
# unrelated to Zeus: in-flight loot-CTA work changed the loot button to telegram.me/{loot} (no ?start=)
# but the test still asserts the old ?start=loot_free URL. Do not "fix" it; just confirm it's the only
# failure and that nothing you touched caused a new one.

## Stop condition
Review doc written; A–E answered with cited evidence; one next-slice recommendation. Do not implement it.
```

---

## Why this handoff exists

Phase 0 shipped a self-consistent architecture, but the highest-value slices carry decisions where a single
author is easy to fool:

- the **two-lock session model** (real defense-in-depth vs accidental duplication),
- the **"Bot-API co-hosting is cheap"** assumption (true on paper; PTB event-loop reality untested),
- **sequencing** the first buildable slice (`zeus_core` extract vs read-only router).

An independent reviewer with fresh eyes on the same sources is the cheapest way to catch a wrong assumption
before it becomes committed code. Feed the review back into this repo (`ZEUS_MONOLITH.md` gets a corrections
pass) before starting Phase 1.
