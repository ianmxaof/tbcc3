# Reverse report: Revenue pipe P0 + loot gate

**Date:** 2026-07-25  
**Status:** Phase 1 complete · Phase 2 (Linkvertise) pending operator

## Session architecture (changed from handoff)

Original handoff proposed `sync-admin-session.ps1` (copy home session → island). **Rejected** — copied keys die on dual-IP.

**Shipped instead:** Island **independent Telethon login** (second auth key, same account `@FreeUseDistrictManager` / `7787282561`).

| Step | Result |
|------|--------|
| Quarantine dead island sessions | `/opt/tbcc/sessions-quarantine/20260725T174650Z` |
| Interactive login in one-off worker container | OK — `admin`, `admin_poster`, `admin_import` created 17:49 UTC |
| `docker compose up -d --force-recreate api worker worker_post` | All **Up** |

Home + island can now both use Telethon without `AuthKeyDuplicatedError`.

## worker_post verification

```
api           Up
worker        Up
worker_post   Up
beat          Up
payment_bot   Up
loot_bot      Up
```

**Sample successful send (worker_post logs):**
- `Sent scheduled post 1 to -1003927742839` (AOF LOOT ROOM)
- VIP mirror: `scheduled post 1 → VIP`
- Checkout follow-up: `chat=-1003927742839` plan=10
- **No** `AuthKeyDuplicatedError` in tail logs

## Growth hub

Loot Room scheduler (`main`): **ok: true**, scheduler_id=1, 113 variations, pin_after_send=true.

## Overdue backlog

- **Before restart:** 134 overdue scheduled posts (API `status=overdue`)
- **After ~25s:** still 134 (drain in progress — expect 30–60 min for full clear)
- Monitor: `GET https://api.powercore.app/scheduled-posts/?status=overdue&limit=5`

## Phase 2 — Linkvertise loot gate (DONE 2026-07-25)

| Field | Value |
|-------|--------|
| New gate slug | `https://link-center.net/1367336/dl1P4gLUfX0L` |
| Destination | `https://telegram.me/+97f4Crv3G1RkMGU5` |
| Code | `backend/app/data/aof_manual_gate_links.py` key `loot` |

Replaces dead `S4isAVBXklrz` → `+NWathiLSqZ1lMzlh`. Island schedulers synced after hot-patch.

## Weekend sales blockers remaining

| Blocker | Severity | Owner |
|---------|----------|-------|
| LV loot gate dead destination | High | Operator browser |
| 134-post overdue drain | Medium | Auto (worker_post running) |
| `aof_vip_mirror.py` import fix | Low | Deploy to island image when convenient |
| External income sync (LV login) | Low | Operator |

## Do not do

- Do not `sync-admin-session.ps1` while home relay/schedulers are active
- Do not start home payment/loot bots (409 vs island)
