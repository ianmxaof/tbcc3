Track: CADENCE · CC-1 · 🔄 P0-P1 done, STOP for ACK

# Report: temporary-display cadence (CADENCE track)

**Against:** pasted directive "Implement the CADENCE track: per-lane ~5 single-media posts per day, shallow visible channel history... real mechanisms only"
**Date:** 2026-08-22

## Phase 0 — I0: commit gatekeeper_lane_route.py

**Status: done.** Commit `d93c5ab`, 1 file, 11 insertions/5 deletions. No dedicated test file exists for this module yet (noted as a follow-up, not blocking — the fix was already verified live via 21 real routes earlier this session).

## Phase 1 — dry-run + proposal

### I2: real per-lane post cadence (`scheduled_text_posts`, not `TBCC_LIVENESS_*`)

Queried the island directly. 11 content-lane schedulers, current state:

| scheduler | pool_id | current interval | posts/day now | proposed interval | posts/day proposed |
|---|---|---|---|---|---|
| ABG / LBFM SCHEDULER | 9 | 120m | 12 | 288m | 5 |
| AOF AI SCHEDULER | 2 | 180m | 8 | 288m | 5 |
| AOF ASS SCHEDULER | 8 | 180m | 8 | 288m | 5 |
| AOF BIG TITS SCHEDULER | 4 | 180m | 8 | 288m | 5 |
| AOF BLOWJOB SCHEDULER | 3 | 180m | 8 | 288m | 5 |
| AOF BOP SCHEDULER | 23 | 120m | 12 | 288m | 5 |
| AOF FULL LENGTH SCHEDULER | 25 | 180m | 8 | 288m | 5 |
| AOF GOON SCHEDULER | 22 | 120m | 12 | 288m | 5 |
| AOF MILF SCHEDULER | 7 | 180m | 8 | 288m | 5 |
| AOF PUBLIC / VOYEUR SCHEDULER | 6 | 180m | 8 | 288m | 5 |
| AOF TABOO SCHEDULER | 5 | 180m | 8 | 288m | 5 |

All 11 currently have `pin_after_send=false`, `delete_after_pin_seconds=NULL`.

Separately, an `AOF CROSS-CHANNEL SCHEDULER` row exists per pool (480m, `pin_after_send=true`) — a distinct cross-promo mechanism, out of scope here, not touched.

**`content_pools.interval_minutes` (15–90m per pool) is currently dead code for all 11 lanes** — `pool_autopost_when_scheduler_enabled()` defaults off, which excludes any pool with its own recurring `scheduled_text_posts` scheduler (all 11 have one) from that path entirely. Confirmed via `post_scheduler.py` read earlier this session. **Proposal: leave `content_pools.interval_minutes` untouched — changing it would have zero effect on real posting cadence.** Only the 11 `scheduled_text_posts.interval_minutes` values need to move.

### I5: singles vs albums — already satisfied, no change needed

`content_pools.album_size = 1` on all 11 lane pools already. Nothing to apply.

### I6: hub auto-approve — confirmed on, one gap

- `TBCC_GATEKEEPER_HUB_AUTO_APPROVE=1` — explicitly set on island.
- `TBCC_STORAGE_DEPOSIT_AUTO_APPROVE` — unset on island, but defaults to `"1"` in code (`storage_deposit_auto_approve.py`), so functionally already on. Not yet pinned explicitly the way its sibling is. **Proposal (Phase 2): add to `seed-island-env-from-home.ps1`'s `$forceKeep`, matching the pattern already used for `TBCC_GATEKEEPER_HUB_AUTO_APPROVE`** — low-risk, no behavior change, just removes drift risk.
- `.env.example` audit: no comment anywhere in the repo implies `TBCC_FORMAT_ENGINE_MESSAGE_RETENTION` controls channel display — checked, not present. Nothing to fix.

### I4: backlog congestion — **real problem, interval tuning alone will not fix it**

Approved-media count per lane pool, right now:

| pool | lane | approved |
|---|---|---|
| 2 | AI | 35 |
| 4 | big_tits | 1 |
| 7 | milf | 1 |
| 3, 5, 6, 8, 9, 22, 23, 25 | blowjob, taboo, **voyeur**, **ass**, abg, goon, **bop**, full_length | **0** |

Voyeur, bop, and ass — the three lanes the directive names for I4 evidence — all show **zero** approved backlog right now. Lengthening their scheduler interval to 288m will *slow the clock*, but there's nothing behind the clock to congest. This isn't a cadence problem, it's the same upstream deposit/approval flow INBOX-PIPE was fixing — media has to actually reach `status='approved'` in these specific pools before "backlog ahead of the clock" means anything. **I'm not able to honestly evidence I4 for these three lanes from interval tuning alone.** AI (pool 2, 35 approved) is the one lane where congestion is real and would show immediately at any interval ≥ ~24m (35 items / 5-per-day ≈ 7 days of runway).

Recommend: apply the interval change regardless (it's correct and wanted either way), but scope I4's evidence to AI pool for Phase 3, and flag voyeur/bop/ass as blocked on deposit volume, not cadence.

### I3: shallow history — real tension, need your call before I apply anything

`delete_after_pin_seconds` only fires after `pin_after_send` succeeds (confirmed in `scheduled_post_service.py`), and the API ceiling is 3600s (1 hour) — both exactly as your gotcha flagged. None of the 11 lane schedulers currently pin.

The tension: at the proposed 288-minute (4.8-hour) interval, a post pinned-then-deleted after the max 3600s would leave the channel visibly **empty for roughly 79% of each cycle** (3.8 of every 4.8 hours) before the next post arrives. That reads as "dead channel," not "party board" — the opposite of the doctrine intent, unless flashing-then-empty is actually what's wanted.

Three options, not deciding among them for you:

**A. Pin + delete at the 3600s ceiling anyway.** Simplest, uses only existing fields. Channel is empty most of the time between posts.

**B. Rolling-window prune instead of per-post delete.** A small new periodic script (`tbcc/backend/scripts/`) that keeps only the last N messages per lane channel, pruning older ones — channel always shows *something* (last 3–5 posts), never fully empty, closer to "shallow but alive." Needs a new idempotent script, not just a field change — directive's scope explicitly allows this ("optional small script... preferred over one-off SQL") but it's more code than A.

**C. Leave delete_after unset for now.** With only 5 posts/day and most lanes starting from near-zero backlog (see I4), "the archive is too deep" isn't actually the live problem yet — it will be in weeks, not now. Defer I3 until I4's backlog gap is closed and there's real volume to prune.

**My recommendation: C now, B later if/when volume justifies it.** But this is a doctrine call, not a technical one — over to you.

## Phase 2 — not started, waiting on your ACK

Will apply once you pick: (a) the I2 interval change (I'd apply this regardless unless you say otherwise), (b) the I6 forceKeep pin, (c) your I3 choice from A/B/C/other.

## Phase 3 — not started

Backlog evidence, scoped to AI pool given the I4 finding above, pending Phase 2.

## Constraints honored

No `git add -A`. No stash/other-session files touched. `content_pools.interval_minutes` and `album_size` left untouched (already correct / dead path). No deletes applied. No doctrine decided.

---

**STOP for Cursor ACK on the I3 delete-window choice (A/B/C) and confirmation to proceed with I2's interval bump before Phase 2.**
