# Listening Relay — operator runbook

**Last updated:** 2026-07-26  
**Island:** `api.powercore.app` (revenue VPS). **One-host rule:** only island holds live `admin.session` — home stack off.

---

## What it does

Posts **now playing** (Last.fm poll + IFTTT/webhook) to a Telegram channel or **random AOF network lane**, with optional ASCII beats, copy-block follow-ups, Buffer/X fan-out, and **loot goblin** spawns.

| Component | Transport | Queue |
|-----------|-----------|--------|
| Main relay HTML (+ text copy follow-ups when flag on) | Bot API (`TBCC_RELAY_USE_BOT_API=1`) or Telethon poster | `ops_relay` / `post` |
| Goblin announce + TTL delete | Loot bot Bot API | `ops_relay` |
| Scheduled pool albums / VIP mirror | Telethon `admin_poster` | `post` |

---

## Bot admin checklist

Before enabling relay or goblin on a destination:

1. **@aof_lootgod_bot** must be **admin** in every channel relay can land (random network = all enabled AOF channels).
2. Forum topics: bot needs **post in topics** if `message_thread_id` is set.
3. Goblin **Claim loot** deep-links to `@aof_lootgod_bot?start=goblin_<token>` — token is case-sensitive.

Verify on island:

```bash
# Dashboard → Listening relay → Test post
# Or API (internal key):
curl -s -X POST https://api.powercore.app/listening-relay-settings/test-post \
  -H "X-Internal-Api-Key: $TBCC_INTERNAL_API_KEY"
```

Check `listening_relay_post_log.extra.transport`:
- `bot_api` — Phase 5a path (no poster lock)
- `telethon` — legacy path

---

## Environment flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `TBCC_RELAY_USE_BOT_API` | `0` | `1` = main body + **text-only** copy follow-ups via loot bot Bot API |
| `TBCC_RELAY_PAUSE_WHEN_SCHEDULER_OVERDUE` | on | Relay skips send when scheduler backlog is hot |
| `goblin_mode_enabled` | dashboard | Goblin spawns on scrobble (DB settings row) |
| `goblin_spawn_chance` | `0.20` | Per-scrobble roll when mode on |
| `goblin_cooldown_minutes` | `120` | Min gap between goblin spawns |
| `goblin_max_per_day_utc` | `3` | UTC day cap |
| `goblin_claims_cap` | `5` | First N tappers get complimentary pull |
| `goblin_announce_ttl_seconds` | `45` | Bot API deletes announce; **token stays valid until cap** |

Set on island in `infra/.env.revenue-island` (worker + api pick up via `env_file`):

```bash
TBCC_RELAY_USE_BOT_API=1
```

Recreate after change:

```bash
cd /opt/tbcc/infra
docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island up -d --force-recreate api worker
```

---

## Goblin doctrine (locked)

- **Announce** = short FOMO beat in channel (~45s visible).
- **Grant** = deep-link only; cap-limited complimentary pull (same class as free pull).
- Announce delete ≠ token revoke.
- Spawn tied to **listening relay scrobble**, not scheduler posts.

Revoke a bad drop:

```bash
curl -s -X POST https://api.powercore.app/goblin/revoke \
  -H "Content-Type: application/json" \
  -H "X-Internal-Api-Key: $KEY" \
  -d '{"token":"<token>"}'
```

---

## Rollback

| Issue | Action |
|-------|--------|
| Relay posts fail on Bot API | `TBCC_RELAY_USE_BOT_API=0` + recreate worker/api |
| `lock_busy` on relay rows | Enable Bot API flag; confirm relay not on `post` queue |
| Goblin spam | Lower `goblin_spawn_chance` or disable `goblin_mode_enabled` |
| Wrong channel | Fix dashboard destination or random-network toggle |

No migration down required — flag-only.

---

## Phase roadmap

| Phase | Status | Notes |
|-------|--------|-------|
| 1–3 | Shipped | Admission gate, bounded poster lock, post log |
| 4 | Shipped | Goblin v1 (Bot API announce) |
| 5a | Shipped (flag) | Bot API main + text follow-ups |
| 5b | Planned | Media copy follow-ups via `file_id` / R2 |
| 5c | Planned | Default Bot API on island; remove Telethon hybrid |

Detail: `docs/handoffs/2026-07-26_relay-bot-api-phase5-plan.md`

---

## Smoke after deploy

```powershell
.\scripts\revenue-island\deploy-island-live.ps1 -SkipTunnel -SkipSeeds
```

```bash
curl -fsS https://api.powercore.app/health
curl -fsS https://api.powercore.app/health/telegram | jq .import_shares_admin_file
# Test post → confirm post_log status=sent, extra.transport=bot_api
docker logs infra-worker-1 --since 5m 2>&1 | grep -i relay
```

---

## Related docs

- `docs/handoffs/2026-07-25_listening-relay-scheduler-isolation.md`
- `docs/loot-room-pinned-instructions.md` — LRG commons copy
- `docs/REVENUE_ISLAND.md`
