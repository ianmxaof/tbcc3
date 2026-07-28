# VIP reprice — 30-day baseline (capture before announce)

**Date:** 2026-07-27  
**Status:** **Not captured** — island API refused connection during deploy session.

## Why this matters

Kill criterion for the $18 VIP floor: **VIP revenue below prior 30-day baseline AND key units flat** after 30 days → rollback floor to $12, not $6.

## Capture when stack is up

```powershell
# TBCC MCP (Cursor) or curl with internal key
# analytics_income_summary days=30
```

Record manually:

| Metric | 30d before reprice | Notes |
|--------|-------------------:|-------|
| VIP subscription revenue (USD) | | Gumroad + Stars + crypto |
| Loot key revenue (USD) | | m60–m15 |
| VIP new units | | |
| Loot key units | | |
| Gate revshare (USD) | | |
| Curated / AI pack revenue | | |
| Companion stars revenue | | |

Paste results into this file or `docs/handoffs/2026-07-27_module-b-loot-economy-designer.md` § baseline.

## Reprice effective

- Code ladder: **$18 / $48 / $90 / $168 / $300** (`aof_vip_membership.py`)
- Gumroad product `ynnulc`: **operator must update dashboard prices**
- `TBCC_GUMROAD_PRODUCT_MAP`: legacy + new `price:*` keys in home `.env` and island env
