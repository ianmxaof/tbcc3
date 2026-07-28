# VIP reprice — 30-day baseline (captured 2026-07-27)

**Island Postgres snapshot** — before public $18 VIP announce. Use as kill-criterion reference.

## Income (30 days)

| Source | USD | Count |
|--------|----:|------:|
| subscription_stars | **39.24** | 9 |
| affiliate | 12.50 | 1 |
| subscription_manual | 12.00 | 2 |
| linkvertise | 9.00 | 1 |
| **Total** | **~72.74** | 13 |

## Subscriptions (30d window via `expires_at`)

| Plan | Units | Stars |
|------|------:|------:|
| AOF Main — 30 days (legacy) | 8 | 4000 |
| Loot Room 24h — 60min | 3 | 450 |
| AOF VIP — 1 Month (pre-reprice) | 2 | 1000 |
| Loot Room 24h — 30min | 1 | 320 |

## wk30 beacons (hits at capture)

| Slug | Hits |
|------|-----:|
| wk30-loot-free | 1 |
| wk30-lv-loot | 1 |
| wk30-x-hub | 1 |
| wk30-bait-batch | 0 |
| wk30-ops-sprint | 0 |

Note: wk30 hits were mostly **curl smokes + TelegramBot previews** — beacon notify spam fixed 2026-07-27 (`TBCC_CLICK_BEACON_INSTANT=0`, bot UA filter).

## Kill criterion (30d post-reprice)

Rollback VIP floor to **$12** only if **both**:
1. VIP subscription revenue (stars + gumroad + manual) **below ~$40/mo run-rate**, and
2. Loot key units **flat or down** with no pack uplift.

## Re-run

```bash
bash /tmp/island_baseline.sh   # on VPS, or use island_baseline.sh in .tbcc-run/
```
