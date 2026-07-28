# MODULE B — LOOT ECONOMY DESIGNER

**Date:** 2026-07-27  
**Depends on:** `2026-07-27_module-a-stack-architect.md`  
**Status:** Complete — **$18 VIP floor implemented in code** (deploy + Gumroad pending operator).

## Executive summary

- VIP beats keys on **certainty** (P≥7 = 100% daily vs 30.6% m15), not volume. At $6/mo vs $5.76/day keys were irrational.
- **Floor chosen: $18/mo (1500⭐)** — not $15 (1500 cents collides with legacy quarterly in `VIP_PRICE_CENTS_TO_RECURRENCE`).
- **`bonus_album_draws` applied** — `album_size = min(12, base_rarity + bonus)` in `loot_roll_preview.py`.
- Lane Pass = **content door only** — no roll perks until keys/VIP ladder is honest.
- MEGA = deal only at **≥3 curated packs/month** ($25 vs 2×$12 = penalty).
- Battle Pass = defer; progression-only if ever built.

## Roll-table economics (base weights, sum 98)

| Surface | E[tier] | P(≥7) | Media EV / 24h |
|---------|--------:|------:|---------------:|
| Free | 2.80 | 0 | 1 (lifetime 5) |
| m60 | 4.33 | 20.4% | 103.8 |
| m45 | 4.33 | 20.4% | 138.4 |
| m30 (+1 draw fixed) | 4.33 | 20.4% | 255.7 |
| m15 (+1 shift, +2 draws) | 5.31 | 30.6% | 701.4 |
| VIP daily | 7.63 | 100% | 1 item/day (30/mo) |

## VIP ladder (implemented)

| Term | USD | Stars | Cents (Gumroad) |
|------|----:|------:|----------------:|
| 1 mo | **18** | 1500 | 1800 |
| 3 mo | 48 | 4000 | 4800 |
| 6 mo | 90 | 7500 | 9000 |
| 1 yr | 168 | 14000 | 16800 |
| 2 yr | 300 | 25000 | 30000 |

Legacy cents keys **retained** in map for grandfathered pings: 600, 1500, 3000, 5400, 10000.

**Grandfather:** Gumroad default (existing members keep old price unless operator applies change). Stars = pay new price on next purchase.

**Kill criterion (30d):** VIP revenue below baseline **and** key units flat → rollback floor to **$12** (1000⭐), never $6.

## Discrimination ladder

| Rung | Sells | Must not sell |
|------|-------|---------------|
| Free / daily micro | Habit | Odds, clean |
| Keys m60→m15 | Volume + modifiers | Clean vault |
| Lane Pass | One lane 24h | Roll shift |
| Curated Pack | Permanent seal | Odds |
| MEGA | Month wrap | Cheaper than 2 packs |
| VIP | Certainty + vault | Key-equivalent volume price |
| Founder $500 | Permanence + recovery | Discount VIP |

## Lane Pass / Glimpse / MEGA

| SKU | Price | Ship rule |
|-----|------:|-----------|
| Lane Pass | $3 | **Do not sell** until invite worker + `grant_entitlement`; strip roll perks from copy |
| Glimpse | promo | Checkpoint API live; poster not wired; 0/11 lanes ready for subtopic |
| Curated Pack | $12 | Zip path live when stocked; Pack #1 from ASS |
| MEGA | $25 | Requires ≥3 packs/month or exclusives |

## Modifier doctrine

- No Stars shop for modifiers (melts key EV).
- Later: key addon (+1 guaranteed slot), pity counter on `pity_steps_json`.

## Deploy checklist (operator)

1. **Gumroad** `ynnulc` — set five tier prices to $18 / $48 / $90 / $168 / $300; confirm existing-member grandfather behavior.
2. **Island env** — add `TBCC_GUMROAD_PRODUCT_MAP` keys: `price:1800`, `price:4800`, `price:9000`, `price:16800`, `price:30000` → plan ids (keep legacy `price:600` etc.).
3. **Reseed plans** — `py -3.13 scripts/seed_aof_shop_and_loot.py` (or island deploy script) to push Stars/USD to `subscription_plans`.
4. **Deploy backend** — `tbcc/scripts/revenue-island/deploy-island-live.ps1` after merge.
5. **Baseline** — capture 30d VIP + key revenue before announcing (MCP `analytics_income_summary` when stack up).

## Files changed (2026-07-27)

| File | Change |
|------|--------|
| `backend/app/data/aof_vip_membership.py` | $18 ladder + additive cents map |
| `backend/app/services/loot_roll_preview.py` | `bonus_album_draws` → album size |
| `backend/app/services/fulfillment_entitlement.py` | Grant on every fulfillment |
| `backend/app/services/kit_buyer_capture.py` | Gumroad email → Kit (opt-in) |
| `backend/app/api/subscriptions.py` | Wire entitlement + Kit |
| `backend/app/api/webhooks_payment.py` | Pass buyer email from Gumroad |
| `backend/scripts/seed_aof_shop_and_loot.py` | Full legacy+current PRODUCT_MAP builder |
| `docs/handoffs/2026-07-27_vip-reprice-baseline.md` | Baseline capture template |
| `docs/handoffs/2026-07-27_curated-pack-1-ass-runbook.md` | Pack #1 operator steps |

## Next (week 3–4)

- Entitlement `grant_entitlement()` on fulfill
- Gumroad email → Kit
- Daily micro-pull (tier ≤2, streak)
- Curated Pack #1 seal + zip
