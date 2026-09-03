# Island ops — empty pools + celery_ops health lie — Phase 3 report

**Reverse report for forward directive** `tbcc/docs/handoffs/2026-09-03_island-ops-empty-pools.md` (`ACTIVE for /cc-run — Phase 3` section)
**Executed by:** Claude Code `/cc-run`, 2026-09-03 ~21:45–22:10Z
**Phase:** 3 (I1–I4) — **STOP for Cursor `/cc-report` ACK**. Phase 4 not started.

---

## Summary

I1 (pause pool 8) and I2 (worker album-session env) both done and deployed live. I3 (durability dry-run) is now blocked on **pure Telethon lock contention** — the config bug from Phase 2 is confirmed fixed (the error changed from a `RuntimeError` about a missing session file to a plain 12s lock-acquire timeout). I4 stays not-actionable — no refill data to act on.

---

## I1 — pause pool 8 (P0) — DONE

`PATCH /pools/8 {"auto_post_enabled": false}` → 200, confirmed via `GET /pools/8` (`auto_post_enabled=false`, `approved_count=24` — plenty of stock, it's the protected-source send that fails, not a stock problem).

**Also paused both recurring schedulers reading from pool 8**, since `ContentPool.auto_post_enabled` does not gate `scheduled_text_posts` (established in Phase 1 — confirmed again here as the reason pool 8 kept failing even via schedulers independent of the pool's own interval cron):
- **#8** "AOF ASS SCHEDULER" (`pool_id=8`, `interval_minutes=288`) — paused via the `pause` field added in Phase 1
- **#30** "AOF CROSS-CHANNEL SCHEDULER" (`pool_id=8`, `interval_minutes=480`, also had `send_failure_streak=1`) — paused

This fully stops the fail mill — matches the directive's "optional: pause its primary scheduler if a recurring job still fires without pool auto_post" (both consumers of pool 8 are now covered, not just the pool-interval cron).

---

## I2 — worker album-composer session env (P0) — DONE, deployed, verified live

Added the same env pair `api` already has to the `worker` service in [docker-compose.revenue-island.yml](tbcc/infra/docker-compose.revenue-island.yml):
```yaml
TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION: /sessions/admin_album
TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION: "1"
```

**Deployed:** synced the compose file to island (`sync-island-files.ps1`, files-only, no container changes), then `docker compose up -d worker` — this recreates **only** `worker` (compose diffs the config and only touches the changed service); confirmed via `docker compose ps` that `api`, `worker_post`, `worker_telegram`, `beat`, and all bot containers kept their pre-existing uptimes untouched, only `worker` recreated.

**Verified live:**
```
docker exec infra-worker-1 sh -c 'env | grep ALBUM_COMPOSER'
→ TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION=/sessions/admin_album
→ TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION=1

GET /health → {"status":"ok",...} (island healthy post-restart)
```

**Confirms the fix actually worked:** re-running `loot_durability_check.py` no longer throws the Phase 2 `RuntimeError: Telegram album composer session is not logged in` — see I3 below, the failure mode changed to a pure lock-acquire timeout, which is a *different* (and expected/known) blocker, not the session-path bug.

---

## I3 — loot durability dry-run (P0, depends on I2) — BLOCKED (Telethon lock contention, not forced)

Ran `python scripts/loot_durability_check.py` on island **three times**, spaced across roughly 10 minutes (interleaved with I2's verification and state checks, not a tight retry loop) after the worker restart settled:

```
Album composer Telethon I/O failed (attempt 1/3): Timed out after 12s waiting for the Telegram account session...
Album composer Telethon I/O failed (attempt 2/3): Timed out after 12s ...
TimeoutError: Timed out after 12s waiting for the Telegram account session. Another TBCC worker is
connected to Telegram (admin/import/poster/album). Wait for it to finish or restart TBCC-Celery and
TBCC-Celery-Post.
```

All three attempts hit the identical 12s timeout. I did **not** restart `worker_post`/`worker_telegram`/any bot to force the lock free — that's explicitly out of scope ("Restart worker_post or full stack 'to free the lock'"). Per the directive's own guidance ("if lock still busy after 2-3 spaced retries mark blocked ... no worker restart"), this is now a documented external stop rather than something to keep forcing.

**Likely contributor:** several bot containers (`payment_bot`, `api`) were recreated shortly before/during this window by a separate, parallel Cursor-driven deploy (the `loot-impulse-sales-table` track — see `CURRENT_DIRECTIVE.md`'s parked section, "deployed image `local-20260903-1432` + hot-patch `shop_promo`"). Those containers reconnecting their own Telethon sessions is a plausible reason the account lock stayed busy across this whole window — not evidence of anything stuck, just concurrent legitimate activity on the same one-Telethon-session constraint.

**Consequence:** no dry-run output, no `restored_total`, `--apply-refill` not run (nothing to act on).

---

## I4 — unpause 23/25/30 only if stocked (P1, depends on I3) — NOT ACTIONABLE (correct, no change)

Since I3 never completed, there is still no evidence any of pools 23/25/30 have approved media. Confirmed unchanged via `GET /pools/{23,25,30}`:
- 23 (BOP): `auto_post_enabled=false`
- 25 (FULL LENGTH): `auto_post_enabled=false`
- 30 (SFW X PROMO): `auto_post_enabled=false`

**Correctly left paused** — no refill occurred, nothing to unpause into.

---

## Verification (directive's block, run as specified)

```
rg -n "TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION" tbcc/infra/docker-compose.revenue-island.yml
→ 3 matches: api (line 79), worker (line 117, new), album_composer_bot (line 306)

GET /pools/8 → auto_post_enabled=false ✓

python scripts/loot_durability_check.py
→ no RuntimeError about admin_album.session (I2 confirmed fixed) — blocked on lock timeout instead ✓/blocked

GET /pools/{23,25,30} → all auto_post_enabled=false, unchanged (no refill happened)

Silent-fail: durability blocked with exact error (Telethon account lock, 12s timeout, 3 spaced
attempts) — pool 8 pause confirmed via GET /pools/8 and scheduler PATCH responses above.
```

---

## Git / deploy

One commit, code + infra:
- `20d0f80` — `docker-compose.revenue-island.yml` worker album-session env (I2)

Pool 8 pause (I1) and schedulers #8/#30 pause were live API mutations, not git changes.

**Not yet pushed this slice** — will push alongside this report commit (established pattern from Phase 1/2).

**Completion gates:**
| Gate | Result |
|------|--------|
| Tests | N/A — infra/config change only, no Python logic touched this phase |
| Migration | N/A |
| Stack | pass — only `worker` restarted (authorized for env pickup, not a lock steal); no bot spawn |
| Extension version | N/A |
| Git | 1 commit (`20d0f80`), pushed alongside this report |
| Scope | 1 file touched (compose) + 3 live API mutations (pool 8, scheduler 8, scheduler 30) |

---

## Not done / recommended follow-ups

1. **I3/I4**: re-run `loot_durability_check.py` dry-run once the Telethon lock is reliably free (a few minutes' clear window, no concurrent bot restarts) — the config blocker is fixed, this should now just work.
2. **Phase 4 (not authorized here)**: Storage Hub poster admin-access verification (Telegram-side, operator only) + `_materialize_pool_media_for_send` try/except hardening so a hard download failure is treated as "skip this item" instead of a doomed forward-restricted retry cascade.
3. Once refill data exists: unpause 23/25/30 and their schedulers (#80/#159) conditionally, as already scoped in Phase 2/3.

---

**Phase 3 done — STOP for Cursor `/cc-report`. Do not start Phase 4.**
