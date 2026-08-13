# Handoff: Revenue pipe P0 (island session + posting) + Linkvertise loot gate

**Date:** 2026-07-25  
**Lane:** Frontier plan/ops (Claude Code or named Plan/Ask) → operator executes island steps  
**Reverse report required:** `tbcc/docs/handoffs/2026-07-25_revenue-pipe-p0-and-loot-gate_report.md`

**Context:** Stars sales cliff ~Jul 22 correlates with Telethon `AuthKeyDuplicatedError` (home + island sharing `admin.session`). Checkout still works on island; **155 failed channel posts vs 18 succeeded** last week starved the funnel. Home re-logged `admin.session` as `@FreeUseDistrictManager` (`7787282561`); island still has stale session; `worker_post` is stopped.

**Cursor is handling separately:** Loot Room scheduler sync, daily loot promo, `strip_vip_affiliate_blocks` bugfix, plan 6 reactivation, income ledger sync. **Operator handles #4** (silent spectacle playbook).

---

## Paste block for Claude Code / frontier

```
Goal
----
Restore revenue-island Telethon posting (session sync + worker_post) and verify scheduled/FOMO posts drain. Fix Linkvertise loot gate so external traffic lands in AOF LOOT ROOM (+97f4Crv3G1RkMGU5), not a dead invite.

Repo: C:\Powercore-repo-main\telegram_bot2\tbcc (git root: telegram_bot2/)
Island: root@5.161.53.91, compose at /opt/tbcc/infra/docker-compose.revenue-island.yml, env .env.revenue-island

Out of scope
------------
- Loot border / reveal card enhancements (silent)
- Home tray payment/loot bots (409 risk — island owns money path)
- Reactivating banned-main buffer mirror to old AOF MAIN GROUP (-1003206350461)
- Listening relay (already on Loot Room, home session fresh)

Phase 0 — Plan (read-only, short)
---------------------------------
1. Read docs/REVENUE_ISLAND.md (loot media session section) and scripts/revenue-island/sync-admin-session.ps1
2. Confirm home has fresh admin.session at tbcc/backend/admin.session (logged in today as 7787282561)
3. Confirm island worker_post + worker are stopped; payment_bot + loot_bot + api + beat still running
4. Write plan: sync order, recreate commands, verification queries — STOP for operator ACK if home tray might still hold admin.session

Phase 1 — Island session sync + worker_post (operator + CC assist)
------------------------------------------------------------------
Prereq: Home TBCC must NOT use admin.session (stop backend/celery that touch Telethon if any).

From tbcc/ on home (PowerShell):
  .\scripts\revenue-island\sync-admin-session.ps1 -HostName root@5.161.53.91

On island:
  ssh root@5.161.53.91 "cd /opt/tbcc/infra && docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island up -d --force-recreate api worker worker_post"

Verify:
  ssh root@5.161.53.91 "docker compose -f /opt/tbcc/infra/docker-compose.revenue-island.yml --env-file .env.revenue-island ps worker_post worker api"
  # worker_post must be Up

Phase 2 — Post drain verification
---------------------------------
Use island API (https://api.powercore.app) or SSH + curl on island localhost:8000:

  curl -s "https://api.powercore.app/growth-hub/status" | jq '.schedulers[] | select(.key=="main")'
  # Expect ok:true, scheduler_id set (Cursor may have synced — if still no_scheduler, POST /growth-hub/sync-schedulers)

  curl -s "https://api.powercore.app/scheduled-posts/?status=overdue&limit=5"
  # Watch overdue count fall over 30–60 min as worker_post drains

  curl -s "https://api.powercore.app/analytics/weekly-summary"
  # Recent failures should NOT show AuthKeyDuplicatedError or strip_vip_affiliate_blocks

Optional one-shot test post (Loot Room channel_id=8):
  curl -s -X POST https://api.powercore.app/listening-relay-settings/test-post

Phase 3 — Linkvertise loot gate fix
-----------------------------------
Problem: Slug https://direct-link.net/1367336/S4isAVBXklrz (key `loot` in backend/app/data/aof_manual_gate_links.py) still destinations to obsolete t.me/+NWathiLSqZ1lMzlh per docs/GATE_LINK_AUDIT.md.

Required destination: https://telegram.me/+97f4Crv3G1RkMGU5 (AOF LOOT ROOM, ident -1003927742839)

Steps:
1. Log into Linkvertise dashboard → find post slug S4isAVBXklrz (or "loot" / AOF LOOT ROOM gate)
2. Change destination URL to https://telegram.me/+97f4Crv3G1RkMGU5 (telegram.me form, not bare t.me/+NWathi…)
3. Save and wait for LV propagation (~minutes)

Verify (operator browser or curl follow):
- Complete gate in incognito OR use LV preview if available
- Lands in AOF LOOT ROOM group, not dead invite
- Growth hub bulletin still uses gate URL as anchor href (slug unchanged); only LV dashboard destination changes

Optional code-side hardening (only if LV dashboard already fixed but bulletin still wrong):
- After sync-schedulers, inspect bulletin_preview for loot entry href
- Do NOT change slug in aof_manual_gate_links.py unless creating a new LV post

Phase 4 — Report + stop
-----------------------
Write tbcc/docs/handoffs/2026-07-25_revenue-pipe-p0-and-loot-gate_report.md with:
- Session sync timestamp, worker_post status
- Overdue post count before/after
- Sample successful channel post (channel name + time)
- Loot gate: destination URL confirmed after LV edit
- Any blockers for weekend sales

Do NOT start home payment/loot bots. Do NOT commit .session files.

Verification commands (summary)
-------------------------------
  ssh root@5.161.53.91 "docker compose -f /opt/tbcc/infra/docker-compose.revenue-island.yml --env-file .env.revenue-island ps worker_post"
  curl -s https://api.powercore.app/health
  curl -s "https://api.powercore.app/analytics/weekly-summary"
```

---

## Quota reminder

Run `/usage` in Claude Code before a long island SSH grind.

## Lane note

Judgment on **whether to re-point plan 6 “AOF Main” SKU** to Loot Room channel — Cursor is reactivating on island; confirm grant target in report if unsure.

## After CC completes

User: `read the CC report` in Cursor → `/cc-report` skill → ACK before next revenue work.
