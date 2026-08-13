# VIP Productization P0–P4 + P5 + P6-E — Full Ship Report

**Date:** 2026-08-09  
**Island tag:** `ghcr.io/ianmxaof/tbcc-worker:local-20260809-0044`

---

## Shipped (all phases)

| Phase | Status |
|-------|--------|
| **P0** | Comparison CTA on @aofmainhub — **live** (`apply_mainhub_growth --post-now`, scheduler 147 updated) |
| **P1** | Full checkout deal stack default + intro variant |
| **P2** | VIP contrast on footers + daily spotlight |
| **P3** | 48h public exclusive delay on VIP mirror pools (`TBCC_VIP_EXCLUSIVE_DELAY_DAYS=2` default) |
| **P4** | Friday VIP mega → Loot Room public tease (gated link) |
| **P5** | `/status` VIP member home (god roll, mega countdown, companion credits) |
| **P6-E** | 3-day renewal DM loss-framing |

## Island deploy

- **First pass:** failed on `bootstrap_storage_hub_panels` (Telegram flood control) — stack still recreated.
- **Second pass:** `-SkipSeeds` succeeded; image `local-20260809-0044`.
- **Pin refresh:** `apply_mainhub_growth.py --execute --post-now` OK.

## Operator still manual

1. **Loot Room pin** — paste section from `docs/loot-room-pinned-instructions.md` (VIP vs free lanes).
2. **Smoke** — payment bot `/status` as active VIP; `/subscribe` checkout shows full stack; lane post footer shows VIP contrast.
3. **Friday** — confirm weekly mega + Loot Room tease fire (needs `mega_pack` LootModifier stocked).

## Rollback env (island `.env`)

```
TBCC_VIP_CHECKOUT_CAPTION_MINIMAL=1
TBCC_POST_FOOTER_VIP_CONTRAST=0
TBCC_VIP_EXCLUSIVE_DELAY_ENABLED=0
TBCC_VIP_WEEKLY_MEGA_PUBLIC_TEASE_ENABLED=0
```

## Tests (local)

46+ passed across VIP productization suite.
