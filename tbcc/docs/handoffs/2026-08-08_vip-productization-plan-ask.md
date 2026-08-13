# VIP Productization — Claude Code Plan/Ask Handoff

**Date:** 2026-08-08  
**Mode:** Plan / Ask first — **do not implement** until plan is written and operator picks phases.  
**Reverse report:** `tbcc/docs/handoffs/2026-08-08_vip-productization-plan_report.md`

---

## Paste block (Claude Code)

```text
You are working on TBCC (Telegram Bot Command Center) in repo `telegram_bot2` / `tbcc/`.

## MODE: PLAN / ASK ONLY (this session)

Do NOT edit production code in this pass unless the operator explicitly says "implement phase N" after you deliver the plan.

Your job: read the codebase + docs, validate assumptions, and deliver a **shippable implementation plan** with exact file paths, copy drafts, env flags, tests, and operator vs agent split.

When done, write:
`tbcc/docs/handoffs/2026-08-08_vip-productization-plan_report.md`
Then STOP for operator ACK.

---

## PRODUCT PROBLEM (operator diagnosis)

VIP subscriptions under-convert because:
1. Free niche lane channel subs feel they already have "the library" (scroll full lanes in addlist).
2. VIP perks exist in code but are invisible at checkout and on public posts.
3. Value prop is abstract ("Hall Pass") vs tangible comparison (album size, gates, timing, rituals).
4. Checkout often shows minimal caption (`TBCC_VIP_CHECKOUT_CAPTION_MINIMAL=1`) hiding the full deal stack.

Recent scarcity moves that worked: **forwarding disabled** on previews, **public album size = 1** (tease). Need to **productize VIP** and **make existing VIP better**.

---

## STRATEGIC FRAME (locked — plan must align, flag conflicts)

Sell VIP as **one membership with five receipts**, not "another channel":

| # | Pillar | Promise |
|---|--------|---------|
| 1 | **Unified Vault** | One feed vs scattered addlist lanes |
| 2 | **Skip Button** | Direct/ad-free links; public stays gated |
| 3 | **Daily God Roll** | `/viproll` on @aof_lootgod_bot — habit/gacha |
| 4 | **Weekly Mega** | Friday direct folder in VIP only |
| 5 | **Companion bundle** | Gate skip + bonus credits (sweetener, not lead) |

**Public vs VIP comparison (marketing spine):**

| | Free lanes | AOF VIP |
|--|------------|---------|
| Where | Scattered addlist | One VIP feed |
| Album size | 1 (tease) | 3–10 rolled |
| Links | Gated/wrapped | Direct/ad-free |
| Timing | Public schedule | ~60 min early |
| Daily pull | Loot keys/tease | `/viproll` god roll |
| Weekly | Gated/delayed | Direct mega folder |

**Doctrine (do not violate):**
- No tier that is **clean + forwardable + paid** (`docs/LOOT_LANE_ECONOMY.md`).
- Library stays paid; public = taste + gates + delay; VIP = vault + rituals + speed.
- Lane Pass ($3) still shelved — do not wire payment in this plan unless operator overrides.
- Never spawn live Telegram bots or touch operator `.env` / sessions.

**Pricing context (already shipped):**
- VIP floor $18/mo (1500⭐); intro month $10 first-time (`VIP_INTRO_SKU`).
- See `docs/handoffs/2026-07-27_vip-reprice-baseline.md` and `2026-07-27_module-b-loot-economy-designer.md`.

---

## READ FIRST (in order)

1. `tbcc/docs/SPRINT_STATE.md` — in flight, do not touch
2. `tbcc/docs/LOOT_LANE_ECONOMY.md` — watermark tiers, funnel
3. `tbcc/docs/handoffs/2026-07-27_module-b-loot-economy-designer.md` — VIP vs keys economics
4. `tbcc/docs/TEST_MAP.md` — AOF/VIP test files

---

## KEY CODE PATHS (validate what's real vs aspirational)

| Area | Paths |
|------|-------|
| VIP deal copy / checkout | `backend/app/services/aof_vip_deal_copy.py`, `aof_main_group_copy.py`, `fiat_checkout_labels.py` |
| VIP fulfillment welcome | `backend/app/services/aof_vip_fulfillment.py` |
| VIP perks (companion credits) | `backend/app/services/aof_vip_perks.py` |
| Feed rhythm (album 1 vs 3–10) | `backend/app/services/aof_feed_rhythm_v2.py` |
| VIP mirror + early drop | `backend/app/services/aof_vip_mirror.py`, `aof_vip_early_drop.py`, `poster_worker.py` |
| Weekly mega | `backend/app/services/aof_vip_weekly_mega.py`, `workers/vip_weekly_mega_worker.py` |
| God roll | `backend/bots/loot_bot.py` (`cmd_viproll`), loot API claim |
| Mainhub growth / CTA | `backend/app/services/mainhub_growth.py`, `mainhub_channel_spotlight.py` |
| Network map | `backend/app/data/aof_network.py` |
| Content protection | `backend/app/services/telegram_content_protection.py` |
| VIP intro eligibility | `backend/app/services/vip_intro_eligibility.py` |
| Payment bot checkout | `backend/bots/payment_bot.py` |
| Tests | `tests/test_aof_vip_*.py`, `tests/test_vip_intro_eligibility.py`, `tests/test_aof_vip_fulfillment.py`, `tests/test_aof_vip_deal_copy.py` |

Env flags to inventory in plan: `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL`, `TBCC_NETWORK_ALBUM_SIZE`, `TBCC_AOF_VIP_ALBUM_ROLL_*`, `TBCC_AOF_VIP_EARLY_DROP_*`, `TBCC_VIP_WEEKLY_MEGA_*`, `TBCC_VIP_PERKS_ENABLED`, `TBCC_VIP_COMPANION_BONUS_CREDITS`.

Bots: `@aof_lootgod_bot`, `@aofsubscriptions_bot` (payment), `@aof_secretary_bot`, `@aof_spicybot_bot`. VIP channel ident: `AOF_VIP_IDENT` in `aof_network.py`.

---

## PLAN DELIVERABLES (required in report)

### 1. Current-state audit
- What VIP perks are **implemented + enabled on island defaults** vs copy-only?
- Where does minimal checkout caption hide the deal stack?
- Is weekly mega + early drop actually schedulable/smokeable?
- What % of VIP content is mirror-only vs `AOF VIP POOL` exclusive?

### 2. Gap analysis
- Why free lane subs don't feel pain (specific UX gaps).
- Which perks are invisible at decision moment (checkout, @aofmainhub pin, Loot Room, public post footers).

### 3. Phased implementation plan (numbered, independently shippable)

Proposed priority (reorder if code audit disagrees):

| Phase | Scope | Effort |
|-------|-------|--------|
| P0 | Public vs VIP comparison copy + pin strategy (@aofmainhub, Loot Room) | S |
| P1 | Full checkout value stack (disable minimal caption default or per-surface) | S |
| P2 | Public post footers (early + bigger + direct CTA) on schedulers/posters | M |
| P3 | VIP-exclusive drop policy (% in AOF VIP POOL only; vault_clean robocopy) | M — **judgment** |
| P4 | Friday mega ritual + public tease / delayed public wrap | M |
| P5 | Payment bot `/status` VIP member home (god roll ready, mega countdown, days left) | M |
| P6 | Retention: monthly companion drip, god roll streak, renewal DMs | L |

For each phase: files to touch, new tests, env vars, operator-only steps (island deploy, reseed, pin post), rollback.

### 4. Copy pack (HTML, Telegram-safe)
Draft ready-to-paste:
- Pinned comparison post (full table + one-liner)
- Checkout caption (full stack, intro month variant)
- Public post footer template (with `{minutes_early}` / `{album_public}` / `{album_vip}` placeholders if templated)
- VIP welcome DM refresh (align with pillars)
- Renewal / expiry nudge (3 days before)

### 5. VIP-exclusive content policy (recommendation only)
- Target % VIP-only vs mirrored
- Robocopy `vault_clean` → AOF VIP POOL workflow
- What public lanes should NEVER get (megas, full sets, clean masters)

### 6. Metrics / success criteria (30 days)
- VIP units, intro conversion, renewal rate
- Reference baseline in `2026-07-27_vip-reprice-baseline.md`
- Suggested beacons or dashboard reads if already available

### 7. Out of scope (explicit)
- Lane Pass payment wiring
- New SKU tiers
- Supervisor panel rewrite
- Live bot starts / tray ops
- Gumroad operator changes (document only)

---

## CONSTRAINTS

1. NEVER commit `.env`, secrets, `*.session*`.
2. NEVER start payment/loot bots or `POST /bots/runtime/*/start`.
3. Revenue island is canonical for money — note deploy script `tbcc/scripts/revenue-island/deploy-island-live.ps1` for backend changes.
4. ASCII-only in PowerShell scripts.
5. Match existing HTML copy style in `aof_vip_deal_copy.py` / `aof_main_group_copy.py`.
6. Extension version bump NOT required unless extension touched.

---

## VERIFICATION (for future implementation phases — cite in plan)

```bash
cd tbcc/backend
pytest tests/test_aof_vip_deal_copy.py tests/test_aof_vip_fulfillment.py tests/test_vip_intro_eligibility.py tests/test_aof_feed_rhythm_v2.py -q --tb=short
```

Add any new tests to plan per phase. Map entries in `docs/TEST_MAP.md`.

---

## WORKING AGREEMENT

- This session: **plan doc only** → `2026-08-08_vip-productization-plan_report.md`
- No git commit unless operator asks after review.
- If a phase is trivial (copy-only seed script), note it as "operator paste" vs "code change".
- Call out judgment calls with ⚠️ for operator decision (exclusive %, public delay length, mega tease aggressiveness).

---

## TASK

Produce the full Plan/Ask report per deliverables §1–7. Include a one-page **operator menu** at the top: "Pick P0–P6 to implement in Claude Code grind pass 2."

STOP after writing the report.
```
