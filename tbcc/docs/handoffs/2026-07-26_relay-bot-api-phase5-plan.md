# Phase 5 Plan — Listening Relay → Bot API Delivery (Frontier)

**Date:** 2026-07-26  
**Status:** Plan only — do not implement until operator ACK  
**Lane:** Desktop named · **Frontier (Plan/Ask)** — Opus Thinking High recommended  
**Judgment triggers:** multi-system architecture (extension + backend + bots + island + Telethon/Bot API split); revenue/ops risk (scheduler stall = missed drops); irreversible surface change (relay copy/media parity).

---

## Problem statement

Phases 1–3 reduced relay–scheduler **contention** (admission gate, bounded lock wait, grid-stamp). Phase 4 goblin already uses **loot bot Bot API** for announce/claim — correct split.

**Remaining pain:** Main relay body + copy follow-ups still ride `post_listening_relay_message` → **Telethon poster lock** + `post` queue. Any relay send can still delay or fail scheduled posts (`lock_busy`, overdue pile-up). Island is VM-only with one `admin.session` — contention is structural until relay exits Telethon.

---

## Goal

Move **listening relay Telegram delivery** (main HTML + copy follow-ups) to **Bot API** (payment bot or dedicated relay bot token), same transport class as goblin announce. Keep Telethon for schedulers, pool albums, VIP mirror, scrape hub — **poster lock becomes scheduler-only**.

Success = relay posts no longer acquire `telethon_session_lock`; scheduler overdue admission gate becomes optional safety net, not primary throttle.

---

## Non-goals (Phase 5)

- Changing Last.fm poll cadence, template rotation, or buffer/X fan-out
- Goblin product tuning (spawn rates — separate short Ask)
- Replacing **all** Telethon posts globally
- Invite-link goblin variant from original handoff (superseded by deep-link grants)

---

## Architecture options

| Option | Bot token | Pros | Cons |
|--------|-----------|------|------|
| **A — Loot bot** | `TBCC_LOOT_BOT_TOKEN` | Already on island; goblin code path exists | Loot bot identity in main channel may confuse; must be admin in all relay destinations |
| **B — Payment bot** | `BOT_TOKEN` / payment | Already admin in main hub channels | Payment bot voice in “now playing” feels off-brand |
| **C — Dedicated relay bot** | New env `TBCC_RELAY_BOT_TOKEN` | Clean separation; kill switch independent | Another bot to admin + tray service; token rotation ops |

**Recommendation:** **Option C** if you will post to random AOF network channels + forum topics long-term; **Option A** for fastest cutover if loot bot is already admin everywhere relay lands today.

---

## Delivery parity matrix (must resolve before build)

| Relay feature | Telethon today | Bot API feasibility |
|---------------|----------------|---------------------|
| HTML main + link preview | Yes | `sendMessage` parse_mode=HTML |
| Forum `message_thread_id` | Yes | Supported |
| Silent send | Yes | `disable_notification` |
| Copy block (text) | Yes | Second `sendMessage` or chained task |
| Copy block (media from TBCC library) | `send_file` / album | `sendPhoto`/`sendVideo` via `file_id` or URL — **island may lack local file**; need Saved Messages `file_id` or R2 URL |
| Inline buttons (slot extras) | Yes | `reply_markup` JSON |
| Random AOF channel pick | Yes | Bot must be **member/admin** in each candidate channel |
| ASCII / tryptych multi-followup | Yes | N sequential Bot API sends (no lock) |

**Highest risk:** copy follow-ups that attach **library media** not yet having Bot API `file_id`. Phase 5a may ship **text-only relay** on Bot API; Phase 5b migrates media follow-ups after `file_id` backfill or R2 thumb URLs.

---

## Proposed phased rollout

### Phase 5a — Main body only (MVP)

- New `listening_relay_bot_send.py` — mirror `goblin_announce._tg_post_with_token` pattern
- `post_listening_relay_message` branches on `TBCC_RELAY_USE_BOT_API=1` (default **off**)
- When on: main HTML via Bot API; copy follow-ups **still Telethon** (hybrid) OR deferred to 5b
- Route to `ops_relay` queue (no poster lock)
- Log `transport=bot_api` on `listening_relay_post_log`
- Tests: mock httpx; forum thread id; lock not acquired when flag on

### Phase 5b — Copy follow-ups on Bot API

- Port `send_relay_copy_followups` to Bot API path
- Media: prefer cached `telegram_file_id` on `Media` row; fallback skip-with-note in log
- Tryptych = 3 Celery subtasks or one task loop (no lock)

### Phase 5c — Decommission hybrid

- Default `TBCC_RELAY_USE_BOT_API=1` on island
- Remove Telethon path from relay task (keep code one release behind flag)
- Tune `TBCC_RELAY_PAUSE_WHEN_SCHEDULER_OVERDUE` — may default **off** once relay off lock

### Phase 5d — Ops + docs

- `docs/LISTENING_RELAY.md` runbook: bot admin checklist per destination, VM-only session rule
- Dashboard indicator: relay transport mode
- Metric: `relay_post_log` by transport + `lock_busy` rate should → 0

---

## Revenue / product judgment (frontier)

1. **FOMO stack:** Goblin announce (Bot API, 45s TTL) + main relay (still Telethon until 5a) is **intentionally asymmetric** — goblin is the grab; relay is ambient. Moving relay to Bot API does not change goblin doctrine.
2. **Spawn tuning:** Keep `goblin_mode_enabled=false` until 48h of `lock_busy` + overdue metrics are near zero post-5a; then enable at **0.15–0.20** chance, 120m cooldown.
3. **Channel voice:** If relay bot ≠ loot bot, goblin button still deep-links `@aof_lootgod_bot` — no change to CTA doctrine.

---

## Rollback

- Flag `TBCC_RELAY_USE_BOT_API=0` → instant revert to Telethon path (no migration down)
- No schema required for 5a beyond optional `post_log.transport` column (can use `extra_json` first)

---

## Verification

```powershell
# After 5a on island
curl -fsS https://api.powercore.app/health
# POST test-post with flag on → post_log status posted, no poster lock log line
# Scheduler drain while relay fires → no lock_busy on relay rows
py -3.13 -m pytest tests/test_listening_relay_bot_api.py -q
```

---

## Effort estimate

| Slice | Files | Lane | ~Time |
|-------|-------|------|-------|
| 5a main body | 4–6 | Desktop Auto | 2–3h |
| 5b copy/media | 8–12 | Desktop Auto | 4–6h |
| 5c cleanup | 3–5 | Desktop Auto | 1h |
| 5d docs/ops | 2–3 | Desktop Auto | 1h |

**Do not Cloud Agent** — fits Auto after this plan is ACK'd.

---

## Operator decision needed (pick one)

1. **Relay bot:** A loot / B payment / C dedicated — affects admin work before 5a  
2. **5a scope:** main-only hybrid OK for first ship? (recommended **yes**)  
3. **5a default on island** after smoke, or stay flag-off until 1 week metrics?

ACK this plan → implement 5a on Desktop Auto in a fresh session.
