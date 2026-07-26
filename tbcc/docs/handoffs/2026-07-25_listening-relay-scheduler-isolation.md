# Claude Code Handoff — Listening Relay vs Scheduler Isolation + Loot Goblin Mode

**Date:** 2026-07-25  
**Repo:** `C:\Powercore-repo-main\telegram_bot2\tbcc`  
**Branch:** `fix/loot-border-reveal` (dirty tree — relay work is orthogonal; commit relay slice separately)  
**Reverse report required:** `tbcc/docs/handoffs/2026-07-25_listening-relay-scheduler-isolation_report.md` after each phase  
**Operator context:** Live Last.fm scrobble verified during Cursor session (Sabab — System Skank @ 14:42 UTC); Telegram delivery still blocked by session conflict.

---

## Executive summary (for operator)

Your intuition is **correct**: listening relay is not on the `run_schedule` Beat path, but it **does** contend with schedulers on the **poster Telethon session Redis lock** and the **`post` Celery queue**. That can delay or stall rigid cron drains (`poster_lock_timeout`, overdue scheduler pile-up).

**Liveliness / growth hub** are spiritually aligned (affiliate footers, chaos) but **separate pipelines** — relay does not enqueue `ScheduledTextPost` rows.

**Loot goblin** (ephemeral channel links, <60s attention window) is a strong product fit and can reuse:
- `delete_after_pin_seconds` (migration 096, mainhub liveness uses 45s)
- `relay_random_network_channel` + template/copy slot rotation
- New: Redis TTL “goblin window” + optional `ExportChatInviteRequest` with `expire_date`

---

## Live verification (2026-07-25 ~08:42 PDT)

| Check | Result |
|-------|--------|
| `GET /health` | `ok` |
| Stack | 7/12 up — backend, dashboard, celery, celery_post, celery_post_scheduler, celery_ops, beat |
| Relay poll | **Working** — new row id=5: Sabab — System Skank, ascii_beat=true, copy_followups=1 |
| Telegram send | **Failed** — same session error on all recent rows: auth key used on two IPs (home + island) |
| Discord fan-out | **Working** — `discord_sent: true` on failed rows |

Relay settings (home DB): `enabled=true`, `channel_id=1` (AOF MAIN GROUP), `relay_random_network_channel=false`, `poll_interval_minutes=60`.

---

## Pytest gate (Cursor run)

```text
cd tbcc/backend
py -3.13 -m pytest tests/test_listening_relay_history.py tests/test_listening_relay_target.py tests/test_post_scheduler.py tests/test_celery_routes.py -q --tb=short
```

| Result | Count |
|--------|-------|
| Passed | 17 |
| Failed | 1 — `test_ops_growth_tasks_route_off_home_queue` (stale: `storage_pool_seed` now routes to `telegram`, not `ops_growth`) |
| Relay + scheduler tests | **All pass** |

Fix the stale assertion in Phase 0 (one-line test update).

---

## Architecture diagnosis — why relay hurts schedulers

### What is already isolated (good)

| Layer | Relay | Schedulers (liveness / lane cron) |
|-------|-------|----------------------------------|
| Beat poll task | `poll_listening_relay_lastfm` → **`ops_relay`** queue (Celery-Ops) | `run_schedule` → **`celery`** queue |
| DB rows | `listening_relay_settings` + `listening_relay_post_log` | `scheduled_text_posts` |
| Growth hub wiring | None (own template/footer/copy slots) | `apply_network_liveness`, `sync_main_group_liveness_checkout` |

### Where coupling actually happens (bad)

```
Beat (every 2m)
  └─ ops_relay: poll_listening_relay_lastfm
       └─ queue_listening_relay_post()
            ├─ post_listening_relay_message.delay()  → queue: post  (Celery-Post)
            └─ listening_relay_social_fanout.delay() → ops_relay (Discord/Buffer)

Beat (every 2m)
  └─ celery: run_schedule → check_and_schedule()
       └─ enqueue → post_scheduler queue (Celery-Post-Scheduler)
            └─ drain_scheduled_post_queue()  → acquires POSTER SESSION LOCK

Both paths:
  tbcc:lock:poster_telegram_session
  tbcc:lock:telegram_account_mtproto  (when TBCC_TELEGRAM_ACCOUNT_LOCK=1)
```

**`post_listening_relay_message`** is routed by `poster_worker.*` → **`post`** queue (same as `post_pool` album jobs), **not** `post_scheduler`.

Relay does **not** call `posting_stalled_for_admission()` (thumb warm + view refresh do). So relay can grab the poster lock while schedulers are overdue → `drain_scheduled_post_queue` returns `poster_lock_timeout` (default `TBCC_POSTER_DRAIN_LOCK_TIMEOUT_S=45`).

Follow-up copy blocks + ASCII tryptych extend lock hold time (multi-message send).

### Session conflict (separate but compounding)

Island `docker-compose.revenue-island.yml` explicitly excludes `ops_*` queues, but island **`worker_post`** uses `admin_poster` copied from `admin`. Home relay + island poster sharing auth material → Telethon invalidates session → relay retries hold lock longer.

---

## Product direction — Loot Goblin mode

**Fantasy:** scrobble = goblin spawn. Main post is the “you hear something” beat; a **short-lived raw channel invite** appears in copy block or footer for <60s. Miss it = FOMO. Schedulers stay on rails; goblin is **event-driven** only.

### Suggested mechanics

| Knob | Suggested default | Rationale |
|------|-------------------|-------------|
| `goblin_mode_enabled` | off until Phase 2 | Feature flag on `listening_relay_settings` |
| `goblin_window_seconds` | 45–55 | Matches `delete_after_pin_seconds` liveness pattern; max 60 per user ask |
| `goblin_spawn_chance` | 0.15–0.25 per scrobble | Rare enough to feel special; tune from data |
| `goblin_cooldown_minutes` | 120 | Prevents invite spam / Telegram rate limits |
| `goblin_lane` | random AOF network channel | Use `pick_random_aof_network_channel_id` |
| Ephemeral invite | `ExportChatInviteRequest` + `expire_date=now+window` | True TTL; delete follow-up message after window via scheduled delete task |
| Message delete | `delete_message` after window OR `delete_after_pin_seconds` on a dedicated scheduler row | Reuse poster_worker delete path from scheduled_post_service |

### Metrics to derive (business logic)

| Metric | Source | Use |
|--------|--------|-----|
| **Goblin spawn rate** | `listening_relay_post_log` where `extra.goblin=true` | Balance rarity |
| **Window CTR** | `click_beacon` / UTM on invite link vs impressions | Prove attention diversion |
| **Join conversion** | Telegram member events in window vs baseline affiliate footer | Revenue attribution |
| **Scheduler stall correlation** | `poster_lock_timeout` count vs relay send count per hour | Prove isolation fix worked |
| **Missed scrobble queue depth** | deferred relay jobs when `posting_stalled_for_admission()` | Tune yield policy |
| **Discord-only fallback rate** | `discord_sent && !telegram_message_id` | Ops health |

### Design principles

1. **Schedulers are sacred** — relay must **yield** when `posting_stalled_for_admission()` or overdue scheduler count > 0.
2. **Relay stays random** — template/footer/copy rotation unchanged; goblin is an optional slot modifier.
3. **No island relay** — keep `ops_relay` home-only; island never polls Last.fm.
4. **Dedicated poster session** — `admin_relay.session` OR enforce `admin_poster` only on one host.

---

## Paste this block into Claude Code

```
# TBCC Listening Relay — Scheduler Isolation + Loot Goblin (Lane C)

## Goal (definition of done)

1. **Rigid schedulers protected:** listening relay never causes `poster_lock_timeout` on `drain_scheduled_post_queue` under normal load; relay defers when schedulers are overdue or poster lane is stalled.
2. **Relay stays fun/random:** scrobble-driven posts, template rotation, affiliate footers, ASCII/copy follow-ups unchanged in spirit.
3. **Loot Goblin v1 (optional flag):** on qualifying scrobbles, relay posts include a short-lived channel invite (TTL ≤60s) on a random AOF lane; message auto-deletes after window; spawn rate + cooldown configurable.
4. **Session hygiene:** document + env guard so relay poster session is not shared across home/island (no dual-IP auth key death).
5. **Tests green:** relay + scheduler pytest pass; fix stale celery route test.

Verify:
- `pytest tests/test_listening_relay_*.py tests/test_post_scheduler.py tests/test_celery_routes.py -q`
- Manual: with music playing, relay history row → `status=sent` + `telegram_message_id` after session fix
- Manual: force overdue scheduler + scrobble → relay defers (job requeued), drain succeeds first

## Scope

### In scope
- `backend/app/services/listening_relay_history.py` — admission gate before `post_listening_relay_message.delay`
- `backend/app/services/post_scheduler.py` — expose `posting_stalled_for_admission`, `schedulers_stall_summary` for relay (import-only OK)
- `backend/app/workers/listening_relay_worker.py` — optional defer/requeue when stalled
- `backend/app/workers/poster_worker.py` — route `post_listening_relay_message` to dedicated queue OR add yield hook; goblin delete-after-send
- `backend/app/workers/celery_app.py` — new route `post_relay` queue (or priority); update tests
- `backend/app/services/listening_relay_compose.py` + `listening_relay_target.py` — goblin spawn logic
- `backend/app/models/listening_relay_settings.py` + alembic — goblin flags/cooldowns
- `backend/app/api/listening_relay_settings.py` + `dashboard/src/panels/MiscPanel.tsx` — minimal UI for goblin toggles
- `backend/tests/` — admission gate tests, goblin cooldown tests, celery route fix
- `.env.example` — `TBCC_RELAY_YIELD_WHEN_STALLED=1`, `TBCC_POSTER_TELEGRAM_SESSION` docs

### Out of scope
- Rewriting liveness schedulers or growth hub
- Island deploy (operator/tray only) — note in report
- Buffer armory / X queue changes
- Full click-beacon analytics dashboard (stub hooks OK)

## Constraints & gotchas

- **Queue map:** `poll_listening_relay_lastfm` → `ops_relay`; delivery → `poster_worker.*` → currently **`post`** queue. Scheduler drain → **`post_scheduler`** queue. Both share **poster Redis lock**.
- **`posting_stalled_for_admission()`** already pauses thumb warm + view refresh — relay should use same gate.
- **Existing ephemeral pattern:** `ScheduledTextPost.delete_after_pin_seconds` (45s on mainhub liveness). Reuse delete helper in `scheduled_post_service.py` (~L505).
- **Random lane:** `relay_random_network_channel` + `pick_random_aof_network_channel_id` already exist; goblin should default random lane ON when goblin mode ON.
- **Live blocker:** Telethon session invalidated by dual-IP — operator must re-auth `admin_poster` on ONE host before smoke. Do not commit `.session` files.
- **Stale test:** `test_celery_routes.py::test_ops_growth_tasks_route_off_home_queue` lists `storage_pool_seed_worker` under `ops_growth` but production routes it to `telegram` — update test, do not change route back.

## Verification

```powershell
cd C:\Powercore-repo-main\telegram_bot2\tbcc\backend
py -3.13 -m pytest tests/test_listening_relay_history.py tests/test_listening_relay_target.py tests/test_post_scheduler.py tests/test_celery_routes.py tests/test_listening_relay_admission.py tests/test_listening_relay_goblin.py -q --tb=short
```

```powershell
# After session fix + stack up:
curl -s http://127.0.0.1:8000/listening-relay-settings/history?limit=3
# Expect newest lastfm row status=sent with telegram_message_id
```

```powershell
powershell -NoProfile -File ..\scripts\tbcc-stack-cli.ps1 -Action Status
```

## Working agreement

- Branch: `feat/listening-relay-isolation` off current HEAD (do not mix loot-border WIP unless user asks)
- Commit per phase; never stage `.env`, `*.session*`
- After **each** phase: write `tbcc/docs/handoffs/2026-07-25_listening-relay-scheduler-isolation_report.md` (reverse report structure per claude-code-report skill) then **STOP** for Cursor ACK
- Do not push unless report says operator approved

## Phases

### Phase 0 — Test hygiene + admission gate (no goblin yet)

- Fix `test_celery_routes.py` storage_pool_seed expectation → `telegram`
- Add `relay_may_send_now(db) -> bool` using `posting_stalled_for_admission()` + env `TBCC_RELAY_YIELD_WHEN_STALLED` (default on)
- In `queue_listening_relay_post`, if not allowed: log + set post_log status `deferred` (add status) OR requeue poll with countdown (pick one; document)
- Tests: `test_listening_relay_admission.py`

Verify: pytest phase 0 files

### Phase 1 — Queue / lock isolation

- Route `post_listening_relay_message` to **`post_relay`** queue (new Celery route)
- Document tray: TBCC-Celery-Post consumes `post,post_relay` OR add note to consume `post_relay` on Ops worker with poster session — **prefer Post worker** so relay doesn't starve pool albums; lower priority via separate queue consumed after scheduler drain (document worker `-Q` order)
- Optional: reduce relay lock timeout vs scheduler (relay uses shorter `TBCC_POSTER_MAX_ATTEMPTS` or skips retry on lock wait)

Verify: pytest + `test_celery_routes.py` asserts `post_listening_relay_message` → `post_relay`

### Phase 2 — Loot Goblin v1

- Alembic: `goblin_mode_enabled`, `goblin_window_seconds`, `goblin_spawn_chance`, `goblin_cooldown_minutes`, `goblin_last_spawn_at`
- On scrobble compose: if roll passes, create ephemeral invite for picked lane, inject into copy block ("👺 LINK LIVE 47s" + invite), schedule delete
- Store `extra.goblin=true`, `invite_url`, `expires_at` on `listening_relay_post_log`
- Misc panel: collapsible Goblin section (4 fields)

Verify: unit tests for cooldown + chance; manual smoke with test-post

### Phase 3 — Docs + operator runbook

- Patch `.env.example` and short `docs/LISTENING_RELAY.md` (new): home-only, yield policy, session rules, goblin tuning
- Report metrics hooks (log lines or post_log fields) for stall correlation

Verify: pytest full suite from Verification section

## Reference files

- Lock: `backend/app/services/telethon_session_lock.py`
- Scheduler admission: `backend/app/services/post_scheduler.py` (`posting_stalled_for_admission`, `check_and_schedule`)
- Relay pipeline: `listening_relay_worker.py` → `listening_relay_history.queue_listening_relay_post` → `poster_worker.post_listening_relay_message`
- Ephemeral delete: `scheduled_post_service.py` delete_after_pin; `mainhub_growth.py` 45s example
- Target pick: `listening_relay_target.py`
```

---

## Quota reminder

Run `/usage` in Claude Code before a multi-phase grind. This is mechanical enough for **Sonnet Lane C**; product tuning (spawn rates, copy) needs a short **Cursor Plan/Ask** pass after Phase 2 report.

## Lane note

Judgment on goblin spawn rates and revenue attribution = **Desktop Frontier Plan/Ask** (revenue model + irreversible product feel). Implementation phases 0–2 = **Claude Code**.

## Reverse report

Claude Code writes: `tbcc/docs/handoffs/2026-07-25_listening-relay-scheduler-isolation_report.md`  
Cursor reviews with `/cc-report` before Phase N+1 or deploy.
