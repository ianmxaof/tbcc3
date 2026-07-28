# MODULE A — STACK ARCHITECT

**Date:** 2026-07-27  
**Source:** Frontier prompt run against live TBCC codebase (monetization, loot economy, attribution, companion audits).  
**Status:** Complete — spine for Modules B–H.

## Executive summary

- **Price inversion is the single highest-$ fix.** VIP 1-month ($6 / 500⭐) undercuts m15 24h key ($5.76 / 480⭐) while delivering 30 daily god-rolls at tier-7 floor +2 shift. **Decision (Module B): reprice to $18/mo floor** — see `2026-07-27_module-b-loot-economy-designer.md`.
- **Lane Pass cannot ship** — 0/11 lanes meet 2,500/2,500 readiness; `grant_entitlement()` never called from payment code.
- **Curated Pack shippable before Lane Pass** — ASS lane ~642 items; seal band 250–400. Packs first per `LOOT_LANE_ECONOMY.md` red lines.
- **`bonus_album_draws` unpaid** — m30/m15 marketing promises +1/+2 draws; code echoed JSON only. **Fixed 2026-07-27** in `loot_roll_preview.py`.
- **Gumroad email discarded** — buyer email in `webhooks_payment.py`; no Kit capture.
- **No daily return loop** — 5 lifetime free pulls; no daily micro-pull / streak.
- **Attribution stops at subscriptions** — `income_entries` lacks `traffic_source_ref`; loot keys / companion invisible to source rollup.
- **Companion margin unmeasured** — 25⭐ photo vs 2–3 undress API calls; no COGS constant.

## Revenue stack map (abbreviated)

| Layer | SKU | Price | TBCC hook | 30-day test |
|-------|-----|-------|-----------|-------------|
| Acquire | Gate revshare | RPM | `link_gate_provider.py` | Beacon every LV destination |
| Acquire | Free pull | Free | `loot_free_pull.py` | Hold cap; exhaustion → purchase |
| Acquire | Daily micro-pull (new) | Free | `loot_player_stats` | D7 return; DAU |
| Convert | Loot keys m60→m15 | $1.80–$5.76 | `seed_aof_shop_and_loot.py` | Units after VIP reprice |
| Convert | Curated Pack | $12 | `bundle_storage.py` | Pack #1 from ASS |
| Convert | Lane Pass | $3 | Catalog only | **Do not launch** |
| Retain | VIP ladder | **$18–$300** (repriced) | `aof_vip_membership.py` | ARPU; churn |
| Retain | Buyer email → Kit (new) | Free | `webhooks_payment.py` | List size |
| Multiply | Affiliate rotation | Revshare | `promo_affiliate_rotation.py` | Owned vs rented $/1k |

Full tables: agent transcript Module A run (2026-07-27).

## Cannibalization audit (locked)

1. **VIP eats keys** — fix via reprice + freeze VIP roll power (no floor 8, no album>1).
2. **Lane Pass eats keys if roll perks** — strip perks; content door only.
3. **Packs vs keys** — low; different intent (permanent seal vs odds).
4. **MEGA vs 2× pack** — MEGA only when ≥3 packs/month or exclusives.
5. **Companion vs affiliate** — meter COGS before routing warm traffic to owned bot.

## Attribution plan

- Traffic: `src_<family>_<lane>_<wk>` (e.g. `src_lv_ass_wk31`)
- Beacon slugs match traffic slugs
- Schema: `traffic_source_ref` on `income_entries`; beacon → funnel → conversion join
- Extend `conversions_by_source()` past `subscription_created`

## 90-day roadmap

| Window | Work |
|--------|------|
| Week 1–2 | VIP reprice, bonus draws, entitlement grant, Gumroad→Kit email |
| Week 3–4 | Beacon all gates, attribution migration, daily micro-pull |
| Month 2 | Curated Pack #1, companion COGS, whale seat offer |
| Month 3 | MEGA (if ≥3 packs), Lane Pass only if lane clears readiness |

## Anti-patterns

- Launch Lane Pass now
- Add VIP value to fix conversion
- OnlyFans as primary lane without Telegram bridge
- Loosen free pull / goblin generosity
- Clean + forwardable paid tier

## Open questions

1. Actual revenue split VIP / keys / gates / packs / companion (baseline capture before reprice — island API was down 2026-07-27)
2. Undress COGS per delivered photo
3. Curated set ready to seal + hours per curation pass
4. Gumroad grandfather behavior on price change (operator confirms in dashboard)
5. NSFW email posture for Kit

## Code map

| Topic | Path |
|-------|------|
| VIP ladder | `backend/app/data/aof_vip_membership.py` |
| Loot keys | `backend/scripts/seed_aof_shop_and_loot.py` |
| Lane economy bible | `docs/LOOT_LANE_ECONOMY.md` |
| Readiness | `docs/LANE_READINESS_AUDIT.md` |
| Entitlement stub | `backend/app/services/entitlement_ledger.py` |
| Attribution handoff | `docs/handoffs/2026-07-27_deep-link-attribution-frontier.md` |
