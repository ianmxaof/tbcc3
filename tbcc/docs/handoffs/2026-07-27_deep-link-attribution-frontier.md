# Handoff: Deep link attribution + source ledger (Frontier) — **P0**

**Date:** 2026-07-27  
**Status:** **Implemented (PR1)** — alembic `104_traffic_attribution`; run migration on island before tagged bursts  
**Lane:** Desktop Auto shipped core; operator runs `alembic upgrade head` on island  
**Reverse report required:** `tbcc/docs/handoffs/2026-07-27_deep-link-attribution-frontier_report.md` (optional ops note)

**Priority:** **Above** loot goblin affiliate menus (`2026-07-27_goblin-affiliate-menu-frontier.md` — defer until attribution ships).  
**Sibling playbook:** `tbcc/docs/handoffs/2026-07-27_traffic-firehose-playbook.md` — how to **manufacture** Jul-burst-style weeks once sources are measurable.

**Judgment triggers:** revenue model (which firehose to scale); multi-system (bots + gates + ledger + dashboard); irreversible schema (`source_ref` on money rows).

---

## North star

**Know which traffic source produced buyers like jojobi (Jul 12 whale)** — then **repeat that source on purpose**, not hope for another freak spike.

Jul 12–21 was not magic. It was **conversion stack + unknown inbound** during a window when the **poster mostly worked**. After Jul 21 the pipe broke and attribution was blind — so you could not turn the firehose back on.

**Deliverable:** UTM-style `?start=` / gate / beacon schema + `subscription.source_ref` (or equivalent) + dashboard **conversions by source** (not just hour-of-day).

---

## Jul burst facts (ground truth)

| Date | Stars (island ledger) | Pattern |
|------|------------------------|---------|
| Jul 12 | 970⭐ | **jojobi** — Main + 60m key + 30m key in ~1h |
| Jul 13 | 650⭐ | **B B** — Main + loot key |
| Jul 16–21 | sporadic | Main / VIP / loot keys |
| Jul 21+ | **zero** new Stars | Poster `AuthKeyDuplicatedError`; dead LV loot gate; FOMO loop stalled |

Island funnel (30d): **11** `subscription_created`, **9** unique loot players, **~3** goblin spawns/day cap — **tiny cohort**, high intent when it hits.

**Hypothesis jojobi:** affiliate / mini-app referral traffic OR addlist warm user — **unprovable today** because `?start=` and gate entry are not persisted on subscription rows.

---

## What exists today (gaps)

| Piece | Path | Gap |
|-------|------|-----|
| Bait payloads | `stars_bait_copy.parse_bait_start_payload` — `bait_loot`, `bait_vip`, `cm{N}` | Parsed at `/start`; **not stored** on sub |
| Verify / gate | `verify_funnel`, `human_gate_pacing` | `source=payload` in prompt only |
| Referrals | `payment_bot` `ref_{id}` → `ReferralCode` | User referrals ≠ campaign sources |
| Growth attribution | `growth_attribution.record_growth_attribution` | **Scheduler context** (6h lookback), not `start` param |
| Funnel API | `bot_funnel_analytics.attribution_summary` | **Hour-of-day** only |
| Subscriptions | `subscriptions` table | No `source_ref` / `entry_payload` |
| Income ledger | `income_ledger` | Product label only |
| Click beacon | `click_beacon.py` | Short links + hits — **not wired** to Stars fulfillment |
| LV gates | `aof_manual_gate_links.py` | No per-campaign subid in analytics |

---

## Goal

1. **First touch:** record `traffic_source` when user hits payment or loot bot with any tagged `?start=` or arrives via tagged gate/beacon.
2. **Last touch (optional v2):** update on each tagged re-entry before purchase.
3. **Conversion join:** copy `source_ref` onto `Subscription` + `GrowthAttributionEvent` + income ledger row at `subscription_created`.
4. **Dashboard:** `GET /analytics/bots/funnel` adds `conversions_by_source` and top campaigns.
5. **Playbook integration:** every firehose in `traffic-firehose-playbook.md` uses **registered** source ids.

---

## Proposed `source_ref` schema (Frontier to lock)

### Format

```
src_<family>_<campaign>[_<variant>]
```

| Family | Examples | Entry surface |
|--------|----------|---------------|
| `bait` | `src_bait_loot`, `src_bait_vip` | Stars-bait DM / welcome |
| `loot` | `src_loot_free`, `src_loot_paid`, `src_goblin_<drop_id>` | Loot bot |
| `lv` | `src_lv_loot`, `src_lv_ai`, `src_lv_mainhub` | Linkvertise gate completion → Telegram |
| `x` | `src_x_buffer_wk30`, `src_x_native_hub` | Buffer / X caption |
| `ch` | `src_ch_ass`, `src_ch_loot_room` | Inline channel checkout (lane + post id hash) |
| `ref` | `src_ref_user_<tg_id>` | Existing referral deep links |
| `verify` | `src_verify_loot`, `src_verify_vip` | Verify funnel |
| `sale` | `src_sale_announce` | Sale FOMO post (tag CTA links) |
| `beacon` | `src_beacon_<slug>` | `click_beacon` short link |

**Rules:**

- Max 64 chars; `[a-z0-9_]` only.
- Register campaigns in DB table `traffic_source_registry` (id, label, family, active, created_at) — Frontier decides flat file vs table.
- **Do not** break existing payloads (`bait_loot`, `ref_123`, `goblin_token`, `cm10`).

### Mapping existing payloads (v1)

| Incoming `?start=` | `source_ref` |
|--------------------|--------------|
| `bait_loot` | `src_bait_loot` |
| `bait_vip` / `bait_sub` | `src_bait_vip` |
| `loot_free` | `src_loot_free` |
| `loot` / `menu_loot` | `src_loot_paid` |
| `goblin_<token>` | `src_goblin_claim` (+ `extra.drop_id` in attribution) |
| `ref_<id>` | `src_ref_user_<id>` |
| `cm10` / `c10` | `src_checkout_plan_10` |
| `verify_loot` | `src_verify_loot` |

---

## Data model (Frontier pick one)

### Option A — Column on subscriptions (recommended v1)

```text
subscriptions.traffic_source_ref VARCHAR(64) NULL
subscriptions.traffic_source_first_seen_at TIMESTAMP NULL
```

Backfill: NULL for historical rows.

### Option B — `user_funnel_touch` table (recommended if multi-touch matters)

```text
user_funnel_touch(telegram_user_id, source_ref, first_seen_at, last_seen_at, touch_count, last_payload)
```

Subscription creation copies **first** or **last** touch per env `TBCC_ATTRIBUTION_TOUCH_MODEL=first|last`.

### GrowthAttributionEvent extension

Add columns (or `extra` JSON keys):

- `traffic_source_ref`
- `start_payload_raw` (truncated 128)

Wire `record_growth_attribution(...)` calls in `subscriptions.py` fulfillment path.

---

## Implementation sketch (Auto — after Frontier ACK)

| File | Change |
|------|--------|
| `app/services/traffic_attribution.py` | **New** — parse payload → `source_ref`, `record_touch()`, `touch_for_user()` |
| `bots/payment_bot.py` | `cmd_start` → `record_touch` before bait/verify/ref handlers |
| `bots/loot_bot.py` | `/start` handlers → `record_touch` |
| `app/api/subscriptions.py` | On create → read touch → set `traffic_source_ref` + attribution extra |
| `app/services/growth_attribution.py` | `attribution_summary` → `conversions_by_source` |
| `app/api/analytics.py` | Expose source breakdown |
| `dashboard` | Funnel panel: source table |
| `alembic/versions/10x_traffic_source.py` | Schema |
| `tests/test_traffic_attribution.py` | Payload mapping + fulfillment join |

**Env:**

```env
TBCC_TRAFFIC_ATTRIBUTION_ENABLED=1
TBCC_ATTRIBUTION_TOUCH_MODEL=first
TBCC_ATTRIBUTION_TOUCH_TTL_DAYS=30
```

### Linkvertise / external

- Append `subid=` or register beacon redirect: `https://api.powercore.app/r/<slug>` → gate URL with touch cookie equivalent (Telegram has no cookies — use **distinct bot start** per campaign: `?start=src_lv_loot_wk30`).
- Frontier: one pattern for LV → Telegram (start param on pinned hub link vs gate destination only).

### Sale announce + stars-bait CTAs

Tag outbound URLs in `sale_public_announce.py` and `stars_bait_outreach.py` with registered `source_ref` query on bot links.

---

## Dashboard contract (minimum)

```json
{
  "conversions_by_source": [
    {"source_ref": "src_bait_loot", "subscriptions": 2, "stars": 1000},
    {"source_ref": "src_lv_loot", "subscriptions": 1, "stars": 500}
  ],
  "top_campaigns_7d": [...],
  "unattributed_subscriptions": 8
}
```

Operator can answer: **“Did wk30 LV burst beat stars-bait DMs?”**

---

## Verification

```bash
# After implement — island
curl -s "https://api.powercore.app/analytics/bots/funnel?days=7" | jq '.attribution.conversions_by_source'

# Synthetic touch
# Open t.me/aofsubscriptions_bot?start=bait_loot → complete test Stars sub (sandbox) → row shows src_bait_loot
```

---

## Paste block for Frontier (Plan/Ask)

```
Goal
----
Spec deep-link attribution so we can identify and repeat Jul-12-style buyer sources (jojobi whale).
Ship schema + wire plan only — no code.

Read first
----------
- tbcc/docs/handoffs/2026-07-27_deep-link-attribution-frontier.md (this file)
- tbcc/docs/handoffs/2026-07-27_traffic-firehose-playbook.md
- backend/app/services/growth_attribution.py
- backend/app/services/stars_bait_copy.py
- backend/bots/payment_bot.py (cmd_start)
- backend/app/api/subscriptions.py (fulfillment + record_growth_attribution)
- backend/app/services/click_beacon.py

Deliverable
-----------
1. Lock source_ref schema + payload mapping table (§ above)
2. Pick data model (subscription column vs touch table vs both)
3. First-touch vs last-touch doctrine
4. LV / X / channel / sale-announce tagging rules (no Linkvertise on goblin claim — unchanged)
5. Dashboard + API response shape
6. Migration + backfill strategy
7. How playbook campaigns register sources (registry)
8. One paragraph handoff to Auto implementation order (PR1 schema, PR2 bot touch, PR3 dashboard)

Out of scope: implementing code; goblin affiliate menus; changing spawn rates.

Write report to tbcc/docs/handoffs/2026-07-27_deep-link-attribution-frontier_report.md
```

---

## After Frontier completes

1. User: `read the CC report` → `/cc-report` → ACK  
2. **Desktop Auto:** PR1 schema + touch recording  
3. **Operator:** Run tagged campaigns from traffic-firehose-playbook.md only after PR2 live  
4. **Defer:** goblin affiliate menu until `conversions_by_source` is non-empty

---

## Quota reminder

Run `/usage` in Claude Code before a long spec grind.
