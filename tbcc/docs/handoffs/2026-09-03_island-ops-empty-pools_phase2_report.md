# Island ops — empty pools + celery_ops health lie — Phase 2 report

**Reverse report for forward directive** `tbcc/docs/handoffs/2026-09-03_island-ops-empty-pools.md` (`ACTIVE for /cc-run — Phase 2` section)
**Executed by:** Claude Code `/cc-run`, 2026-09-03 ~21:00–21:40Z
**Phase:** 2 (I1–I4) — **STOP for Cursor `/cc-report` ACK**. Phase 3 not started.

---

## Summary

No config was changed and no pool/scheduler state changed this phase (Phase 1's pauses on pools 23/25/30 and schedulers #80/#159/#189 are exactly as left). I1 got past the Telethon lock this time but hit a **different, config-level** blocker — root-caused, not fixed (touches session env + a worker restart, flagged for operator). I3 (#189) is root-caused with high confidence via log evidence, without needing to force a live session. I4 confirmed healthy. **New finding not in the original scope:** pool 8 (AOF ASS POOL) has been hitting the *identical* failure every ~15 minutes for over two weeks — same underlying cause as #189, much bigger blast radius, not currently paused.

---

## I1 — loot durability dry-run (P0) — BLOCKED on a NEW root cause (not the lock this time)

Ran `python scripts/loot_durability_check.py` (dry-run) inside `infra-worker-1` again. This time it **acquired the Telethon account lock successfully** — the Phase 1 contention was transient, as expected — and got further before failing:

```
RuntimeError: Telegram album composer session is not logged in (admin_album.session).
Set TBCC_ALBUM_COMPOSER_AUTO_COPY_ADMIN_SESSION=1 and restart, or run login_telethon_sessions.py
```

**Root cause (confirmed via compose + code, no live call needed):** the `worker` service in [docker-compose.revenue-island.yml](tbcc/infra/docker-compose.revenue-island.yml) has no `TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION` env var. `album_composer_session_stem()` ([telethon_session.py:47-55](tbcc/backend/app/utils/telethon_session.py#L47-L55)) falls back to the bare default `"admin_album"`, which resolves to `/app/admin_album` — inside the container's **ephemeral filesystem**, never populated. The *actual*, already-logged-in session lives at `/opt/tbcc/sessions/admin_album.session` (confirmed present on the host — `find /opt/tbcc -iname '*.session'`), mounted at `/sessions/admin_album.session` inside every service that has the volume — but only the `album_composer_bot` service (a `profiles: ["bots"]` service, not normally running) sets `TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION: /sessions/admin_album` to actually point there.

**Not fixed this pass** — the fix is a one-line compose addition to the `worker` service:
```yaml
TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION: /sessions/admin_album
```
...followed by a worker restart to pick it up. I did **not** apply this: it touches Telethon session config (a category the operator policy explicitly gates — "Telethon scripts: open admin.session only via `run_telegram_io`... Login script sets the override") and requires restarting the live `worker` container mid-Phase-2, which the directive is cautious about even though this restart isn't "to steal the lock." Left for an explicit operator/Cursor decision rather than a unilateral infra change.

**Consequence:** dry-run never completed — no `restored_total` JSON, no survivor data. `--apply-refill` was **not** run (nothing to act on).

---

## I2 — unpause empty pools/schedulers only after restock — NOT ACTIONED (correctly)

Since I1's dry-run never completed, there is no evidence any of pools 23 (BOP), 25 (FULL LENGTH), 30 (SFW X PROMO) now have approved media. Confirmed via `GET /pools/{23,25,30}` — all three still `auto_post_enabled=false`, unchanged from Phase 1. Schedulers #80/#159 remain `posting_auto_paused_at` set, unchanged. **Correctly left paused** per the directive's own gate ("unpause only after approved_count >0 post-refill") — there was no refill.

---

## I3 — post #189 protected-chat root cause (P1) — ROOT-CAUSED (high confidence), left paused

**Root cause, established from `worker_post` container logs (no live session needed for this one — the poster session is already live and actively posting other pools) plus static code review of the shared materialize path:**

The `_materialize_pool_media_for_send()` / `_is_forward_restricted_send_error()` retry logic ([scheduled_post_service.py](tbcc/backend/app/services/scheduled_post_service.py), also used by [album_service.py](tbcc/backend/app/services/album_service.py) for direct pool posting) is **already correctly wired** everywhere it should be — this is not a "forgot to call materialize" bug. The evidence shows the download-and-reupload workaround itself does not succeed for this source content:

- `docker compose logs worker_post | grep -i 'materialize\|forward\|protected\|download_media'` shows, for **pool 8** (a live, currently-unpaused pool hitting this identically — see below), the full failure sequence: first materialize+send attempt fails `ChatForwardsRestrictedError` → the code's own retry (`album_service.py` lines 85-96) re-materializes and re-sends → **fails again, same error** → falls back to per-item individual send (lines 104-117), each item re-materialized individually → **fails again, same error** → propagates out as the task failure.
- Neither of `_materialize_pool_media_for_send`'s own diagnostic log lines ever appear anywhere in the logs: not `"Re-uploading pool media as ..."` (the success path) nor `"scheduled send: download_media empty ... falling back to raw TL media"` (the documented failure fallback). That means `client.download_media(raw, bytes)` is most likely **raising** immediately rather than returning empty data — the code has no `try/except` around that call inside `_materialize_pool_media_for_send`, so such an exception propagates straight up and is presumably being caught upstream and (re-)classified against the same forward-restricted error text.

**Working hypothesis (not 100% confirmed without a live Telethon inspection of this specific message, which I did not force):** the source chat for this media (very likely the Storage Hub — the internal staging channel is a natural candidate for "Restrict Saving Content" / `noforwards`, by design, to prevent leaks) enforces its protection at the Telegram server level against **download**, not just forward, for any account that isn't an admin/creator of that chat. If the currently-configured poster Telethon account lacks elevated (admin) access to the Storage Hub, `download_media()` fails identically to a plain forward — no client-side materialize trick can work around a server-side restriction the account doesn't have clearance for.

**Recommended fix (not applied — needs operator/Telegram-side verification, not a code change):** confirm whether the poster account has admin/creator rights on the Storage Hub source channel. If not, that's the actual fix (grant access), not a code patch. A secondary, lower-priority code mitigation worth a future pass: `_materialize_pool_media_for_send` currently has no `try/except` around `download_media()` — wrapping it and treating a hard failure as "skip this item" (rather than letting it surface as a generic forward-restricted retry that's doomed to repeat) would stop these pools from burning a full retry-cascade every interval on content that can never succeed.

**Action taken:** none new — #189 stays paused from Phase 1, `posting_auto_paused_at` unchanged, reason still accurate. `pytest tests/test_scheduled_post_media_materialize.py` still green (3 passed) — no regressions, no changes made to this file.

### New finding (outside the original I1-I4 list): pool 8 (AOF ASS POOL) — same bug, much bigger blast radius

Pool 8 is **not** one of the four pools this track has touched (23/25/30/4). It has `auto_post_enabled=true`, `interval_minutes=15`, and `last_posted="2026-08-19T01:45:01"` — **over two weeks stale**. `worker_post` logs show it failing with the exact same `ChatForwardsRestrictedError` cascade (materialize → retry → individual-send, all fail) **every ~15 minutes, continuously** (observed at 20:16:35, 20:32:54, 20:47:08 — i.e. every cycle since at least Phase 1). This is the identical root cause as #189, but live and unpaused, burning a real Telegram API failure cascade every 15 minutes for two-plus weeks.

**Not paused by me** — it was outside this directive's explicit pool list (23/25/30/4) and I did not want to unilaterally expand scope on a pool nobody flagged. **Strongly recommend** the operator either pause `auto_post_enabled` on pool 8 until Storage Hub access is confirmed, or explicitly authorize it for a future `/cc-run` pass.

---

## I4 — pool 4 (BIG TITS) drain check (P2) — CONFIRMED HEALTHY

`content_pools.last_posted` for pool 4 is stale (still `2026-07-26`, matching the CLAUDE.md note that this field isn't authoritative for scheduler-driven posts). Checked the actual scheduler instead: **scheduler #4 "AOF BIG TITS SCHEDULER"** (`pool_id=4`) — `last_posted_at="2026-09-03T20:07:20"`, `send_failure_streak=0`, not paused. Matches Cursor's ACK note ("scheduler #4 posted ~20:07Z"). **Draining normally, no action needed.**

(Three other schedulers also read from pool 4 — #51 network-liveness spotlight, #82 feed-rhythm interjection, #24 cross-channel — all healthy except #24 which has `send_failure_streak=1`, worth a glance but not stuck.)

---

## Verification

```
cd tbcc/backend && py -3.13 -m pytest tests/test_scheduled_post_media_materialize.py -x -q --tb=short
→ 3 passed (no changes made to this file — confirms no regression)

Island: python scripts/loot_durability_check.py
→ RuntimeError (album composer session path misconfigured on `worker` service) — no dry-run output, no --apply-refill run

GET /pools/{23,25,30}: auto_post_enabled=false (unchanged from Phase 1)
GET /scheduled-posts/{80,159,189}: posting_auto_paused_at still set (unchanged)
GET /pools/4 + scheduled-posts pool_id=4: scheduler #4 last_posted_at=2026-09-03T20:07:20, send_failure_streak=0

Silent-fail (external stop): I1 blocked on session-path config gap (not the Telethon lock —
that cleared on retry). Evidence: worker container env dump + docker-compose.revenue-island.yml
diff between `worker` and `album_composer_bot` service blocks.
```

---

## Git / deploy

**No files changed, no commits, no deploys this phase.** All findings this pass were diagnostic (log review, compose/code inspection, live read-only API checks) — no code fix was confident enough to ship without either a live Telethon confirmation I chose not to force, or an infra/session config change I chose not to apply unilaterally.

**Completion gates:**
| Gate | Result |
|------|--------|
| Tests | pass — 3/3, no changes made |
| Migration | N/A |
| Stack | pass — no worker restart, no bot spawn, no session file touched |
| Extension version | N/A |
| Git | no changes to commit |
| Scope | 0 files touched |

---

## Not done / recommended follow-ups

1. **I1 fix**: add `TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION: /sessions/admin_album` to the `worker` service in `docker-compose.revenue-island.yml`, then a scoped restart of just `worker` (not a lock-steal — operator/Cursor call). Re-run `loot_durability_check.py` dry-run after.
2. **I3 fix**: verify poster Telethon account's admin/access level on the Storage Hub channel — this is a Telegram-side check, not a code change. If confirmed as the cause, either grant access or route protected-source pools through an account that has it.
3. **Pool 8 (AOF ASS POOL)**: recommend pausing `auto_post_enabled` now — it's been failing every 15 minutes for 2+ weeks on the same root cause as #189, and is not currently on anyone's watch list.
4. Once I1's session config is fixed and a dry-run completes: re-run Phase 2's I1/I2 (refill + conditional unpause) as a fresh slice.

---

**Phase 2 done — STOP for Cursor `/cc-report`. Do not start Phase 3.**
