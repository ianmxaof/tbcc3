# Handoff: Loot goblin affiliate menu drop (Frontier)

**Date:** 2026-07-27  
**Status:** **Deferred** — run after attribution + traffic firehose playbook  
**Lane:** Desktop named · **Frontier (Plan/Ask)** — Opus Thinking High recommended  
**Reverse report required:** `tbcc/docs/handoffs/2026-07-27_goblin-affiliate-menu-frontier_report.md`

**Priority:** Secondary. **P0 first:** `2026-07-27_deep-link-attribution-frontier.md` + `2026-07-27_traffic-firehose-playbook.md` (manufacture Jul-burst weeks).

**Judgment triggers:** revenue model (affiliate vs Stars/loot-key cannibalization); irreversible product doctrine (goblin surface = FOMO only vs FOMO + affiliate billboard); multi-system (listening relay → goblin Bot API → `promo_affiliate_links` → attribution).

---

## Context

Operator wants **loot goblins to “drop” one of three affiliate link menus** every time they spawn in a **loot lane** (any AOF network channel the listening relay targets — not only AOF LOOT ROOM).

**Visual mocks (operator-provided, not in repo):**

| Variant | Label | Notes |
|---------|-------|-------|
| **V2** | DARK PANEL · AFFILIATE | Dense noir panel; `UNDRESS · GENERATOR` header; full AI TOOLS list |
| **V3** | REVEAL BOARD · AFFILIATE | Checkmark lanes; `tap a lane`; best mobile scan |
| **V4** | UNIFORM GRID · AFFILIATE | ASCII frame / grid chrome; decorative borders |

All three share the same **content buckets**: AI TOOLS affiliates, MAINBOTS (`@aof_secretary_bot`, `@aof_lootgod_bot`, `@aof_spicybot_bot`), SUPPORT (`/loot` · `/subscribe` · `/refer`, boost, addlist, donate), PARTNERS (e.g. Nutaku).

**Parallel work (do not block this handoff):**

- Conversion sprint ran on island 2026-07-27 (`apply-stars-bait`, `sync-album-checkout`, bulletin blast).
- **Deep link attribution** + **traffic firehose playbook** are **P0** — see `2026-07-27_deep-link-attribution-frontier.md` and `2026-07-27_traffic-firehose-playbook.md`. Design `goblin_spawn` subids when this spec resumes so menus don’t paint into a corner.

**Observe in parallel (48–72h):** `/analytics/bots/funnel` + `goblin_drop` / `goblin_claim` rows — baseline only; won’t pick V2/V3/V4.

---

## What exists today

| Piece | State |
|-------|--------|
| Goblin spawn | `listening_relay_compose` → `note_scrobble_for_goblin` → `schedule_goblin_drop` |
| Announce | `goblin_announce.send_goblin_announce` — **short HTML + Claim loot button only** |
| TTL | `goblin_announce_ttl_seconds` default **45s**; Celery `goblin_expire_announcement` deletes message |
| Claim path | `t.me/aof_lootgod_bot?start=goblin_<token>` — complimentary pull in DM |
| Affiliate data | `promo_affiliate_links` + `promo_affiliate_rotation.py`; placements: `links_hub_ai`, `loot_roll`, `telegram_footer`, … |
| Links hub HTML | `build_links_hub_bulletin()` in `aof_growth_hub.py` — same inventory, different aesthetic |
| **Affiliate menu on spawn** | **Not built** |
| V2/V3/V4 templates | **Design mocks only** — no code |

**Spawn caps (production):** `goblin_spawn_chance=0.20`, `goblin_cooldown_minutes=120`, `goblin_max_per_day_utc=3`, `goblin_claims_cap=5`.

**Doctrine (locked — do not violate):**

```text
backend/app/services/aof_loot_goblin_promo.py
- Goblin teasers: clearnet bot deep links only — no Linkvertise on goblin claim paths.
```

Direct affiliate URLs (Undress, DrawAI, etc.) are **not** Linkvertise — but Frontier must still rule on whether they belong on the goblin spawn surface vs only on roll footers / links hub.

---

## Problem / opportunity

Goblin spawns are **rare, high-attention moments** (~3/day network-wide) in content lanes. Today they monetize only via **Claim loot → complimentary pull → upsell in DM**. Affiliate inventory is already curated in DB but **not surfaced at spawn**.

**Risk:** Affiliate menu competes with Claim loot and with inline Stars checkout on the same channel feed. **Opportunity:** Monetize scrobble-attached attention without LV friction.

---

## Goal

On every accepted goblin spawn, deliver **one affiliate menu variant** (V2, V3, or V4 — rotation TBD) in the **same channel** as the goblin announce, sourced from `promo_affiliate_links`, with **attribution-ready URLs** and spam guards.

---

## Non-goals

- Linkvertise gates on goblin claim or menu links
- Changing goblin spawn probability / daily caps (unless Frontier recommends explicit tuning)
- Telethon delivery for menus (stay on **loot bot Bot API**, same as announce)
- Replacing links hub bulletin or scheduler affiliate footers
- Phase 5 relay Bot API migration (`2026-07-26_relay-bot-api-phase5-plan.md`)

---

## Decisions Frontier must lock

### 1. Message shape

| Option | Behavior |
|--------|----------|
| **A — Combined** | Single `sendMessage`: goblin FOMO block + affiliate menu below Claim button |
| **B — Sequential** | Message 1: goblin + Claim; Message 2: affiliate menu (both deleted on TTL?) |
| **C — Reply chain** | Menu as reply to goblin announce (thread visually grouped) |

**Recommendation:** **B** — keep Claim message short; menu is second message. Store `affiliate_message_id` on `goblin_drop` if separate.

### 2. TTL

| Option | Behavior |
|--------|----------|
| **A — Same TTL** | Both messages deleted at `goblin_announce_ttl_seconds` (~45s) |
| **B — Menu persists** | Only goblin announce deletes; menu stays (higher affiliate CTR, more spam risk) |
| **C — Longer menu TTL** | Menu lives 5–15 min; announce still 45s |

**Recommendation:** **A** for v1 (honest scarcity, matches “blink” brand). Revisit if affiliate CTR is zero.

### 3. Variant selection

| Option | Behavior |
|--------|----------|
| Random uniform | `random.choice([v2,v3,v4])` per drop |
| Round-robin | Redis or `drop_id % 3` |
| Per lane | `network_key` → fixed variant for A/B by channel |
| Default + rotation | Ship **V3** only; add V2/V4 in v2 |

**Recommendation:** **V3 only for v1**; add `goblin_menu_variant` column or env `TBCC_GOBLIN_MENU_VARIANT=v3`.

### 4. Content source

| Option | Behavior |
|--------|----------|
| New placement `goblin_spawn` | Seed subset of affiliates; independent rotation cursor |
| Reuse `links_hub_ai` | Same 16 AI tools + partners block as links hub |
| Reuse `loot_roll` | Single-line footer style — **too small** for full menu |

**Recommendation:** New placement **`goblin_spawn`** (max 12–16 AI rows + PARTNERS + MAINBOTS block). Reuse `build_sponsor_link_html()` / `list_candidates(db, "goblin_spawn")`.

### 5. Cannibalization / CTA order

Frontier must answer explicitly:

- Is **Claim loot** still the primary CTA (button only on announce, menu is secondary)?
- Include **Stars /subscribe** line in SUPPORT block or omit on goblin menus?
- Show **one** featured affiliate vs full list?

**Recommendation:** Claim stays **inline keyboard only** on message 1; menu message 2 has **no** competing URL button above the fold — hyperlinks in HTML only.

### 6. Attribution (coordinate with next pass)

Every outbound URL in menu should accept:

```text
?utm_source=aof_goblin&utm_medium=telegram&utm_campaign=goblin_spawn&utm_content=<network_key>&drop_id=<id>
```

Or partner-native subid if template supports `{subid}`. Log `goblin_drop.id` + `channel_id` + `variant` for later ledger join.

### 7. Lane scope

Spawn channel = whatever relay used (`channel_id` on `goblin_drop`). Confirm:

- Include all `AOF_NETWORK_CHANNELS` when relay uses random lane?
- Exclude VIP, PACKS, INBOX, LOOT ROOM-only?

**Recommendation:** All **content lanes** in `AOF_NETWORK_CHANNELS`; exclude VIP (id 17) and INBOX intake if relay never targets them.

### 8. Spam / ops guards

- Respect existing `goblin_max_per_day_utc` + cooldown (no extra menu cap needed if 1:1 with spawn).
- `disable_notification: true` on both messages (match current announce).
- Max HTML length — Telegram 4096; trim affiliate list if needed.

---

## Implementation sketch (Auto — after Frontier ACK)

**New files / edits:**

| File | Change |
|------|--------|
| `app/services/goblin_affiliate_menu.py` | `build_goblin_affiliate_menu_html(variant, db, *, drop_id, network_key)` |
| `app/services/goblin_announce.py` | After announce send, send menu message; store IDs on drop |
| `app/models/goblin_drop.py` | Optional: `affiliate_message_id`, `menu_variant` |
| `alembic/versions/104_goblin_menu.py` | Columns if persisted |
| `scripts/seed_promo_affiliate_links.py` | Add `goblin_spawn` placement to AI rows |
| `tests/test_goblin_affiliate_menu.py` | HTML length, no LV URLs, variant smoke |

**Env (optional):**

```env
TBCC_GOBLIN_AFFILIATE_MENU_ENABLED=1
TBCC_GOBLIN_MENU_VARIANT=v3
```

**Do not** call `post_scheduled_text` sync from API container for goblin paths — Bot API only via `goblin_announce`.

---

## Verification (post-implement)

```bash
# Island — force spawn via relay test or wait for natural scrobble
curl -s https://api.powercore.app/listening-relay-settings | jq '.goblin_mode_enabled, .goblin_spawn_chance'

# After spawn
docker exec infra-api-1 python scripts/goblin_spawn_smoke.py

# Telegram: lane channel shows (1) goblin + Claim, (2) affiliate menu; both gone ~45s later
# Claim still works after announce delete (token valid until cap)
```

---

## Paste block for Frontier (Plan/Ask)

```
Goal
----
Spec loot goblin affiliate menu drop: on every goblin spawn in a network lane, post one of
V2/V3/V4 affiliate menus (operator mocks) sourced from promo_affiliate_links.

Read first
----------
- tbcc/docs/handoffs/2026-07-27_goblin-affiliate-menu-frontier.md (this file)
- backend/app/services/goblin_announce.py
- backend/app/services/aof_loot_goblin_promo.py (doctrine)
- backend/app/services/promo_affiliate_rotation.py
- docs/LISTENING_RELAY.md (goblin caps)

Deliverable (spec only — no code)
---------------------------------
1. Lock decisions §1–8 above (message shape, TTL, variant, placement, cannibalization, attribution, lanes, spam)
2. Pick default variant (recommend V3)
3. Wire diagram: scrobble → drop row → announce + menu → TTL delete → claim path unchanged
4. HTML mock for V3 in Telegram-safe subset (no broken Unicode frames if V4 rejected)
5. Seed plan for goblin_spawn placement rows
6. One paragraph: affiliate menu vs deep-link attribution pass handoff

Out of scope: Linkvertise on goblin; changing spawn rates; Telethon; implementing code.

Write report to tbcc/docs/handoffs/2026-07-27_goblin-affiliate-menu-frontier_report.md
```

---

## Quota reminder

Run `/usage` in Claude Code before a long spec grind.

## After Frontier completes

User: `read the CC report` in Cursor → `/cc-report` skill → ACK → Desktop Auto implements locked spec.
