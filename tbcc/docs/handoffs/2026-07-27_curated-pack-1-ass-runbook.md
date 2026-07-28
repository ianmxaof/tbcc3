# Curated Pack #1 — ASS lane operator runbook

**Date:** 2026-07-27  
**SKU:** Curated Pack — $12 / 1000⭐ (`PACK_DROP` in `loot_lane_economy.py`)  
**Target lane:** AOF ASS (~642 approved items; seal band 250–400)

## Prerequisites

- [ ] VIP reprice deployed (buyers see honest ladder before pack upsell)
- [ ] Operator curation block (4–8 hours) — theme + quality pass, not raw scrape dump
- [ ] Zip ≤50 MiB per part OR use `host_gated` flywheel for large sets

## Steps

### 1. Curate the seal

1. Pull ASS pool approved media (`content_pools` key `ass` / AOF ASS).
2. Select **250–400** items with a clear theme (e.g. "ASS Week 31 · 287 curated").
3. Export masters to a staging folder on Storage Hub.

### 2. Fan-out watermarks (optional promo album)

```powershell
cd tbcc/backend
py -3.13 scripts/robocopy_watermark_cli.py --master PATH\to\masters --out PATH\to\out --execute
```

Use `vault_clean` tier only for internal archive — **paid pack ships light or gated, not clean+forwardable**.

### 3. Build zip + attach to shop plan

**Option A — Dashboard:** Upload zip to Curated Pack plan (`POST …/bundle-zip`).

**Option B — Zip flywheel:**

```text
POST /import/zip-flywheel
destination: shop_bundle
plan_name: Curated Pack
```

Find plan id after seed: `Curated Pack` in `/packs` catalog.

### 4. Promo album (3 images)

- Reuse pattern from `seed_ai_curated_packs.py` (3-image promo album in catalog).
- List in payment bot `/packs` with curation proof in copy.

### 5. Smoke purchase

1. Stars or crypto buy Curated Pack on island payment bot.
2. Confirm DM zip delivery (`bundle_storage` → `reply_document`).
3. Confirm `buyer_entitlements` row `kind=curated_pack` (wired 2026-07-27).

### 6. Do not

- Sell Monthly MEGA until **≥3** curated packs shipped this month.
- Launch Lane Pass until per-lane invite worker exists.

## Success metric

**≥4 units per curation hour** on first pack. Below that → monthly cadence, not weekly.

## TBCC hooks

| Piece | Path |
|-------|------|
| Plan seed | `seed_aof_shop_and_loot.py` → `seed_lane_economy_skus` |
| Zip storage | `bundle_storage.py` |
| Fulfillment | `subscriptions.py` + payment bot bundle DM |
| Entitlement | `fulfillment_entitlement.py` |
