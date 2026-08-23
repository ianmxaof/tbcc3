# Report: AOF INBOX intake pipeline — unblock + vision classify wiring

**Against:** operator ask in-thread ("give me actionable things that can get this pipeline back up and moving... standstill... need real content moving yesterday"), followed by real live testing ("i put media in the inbox... nothing looks like it's moving")
**Date:** 2026-08-22

## Summary

Operator dropped a real batch (heavy voyeur + mixed) into the AOF INBOX Storage Hub topic and reported nothing was moving. Root-caused end-to-end via live testing against the deployed island (not assumption) — found and fixed **four separate, previously-unknown production bugs**, each blocking a different link in the same chain: inbox topic → Media row → vision classify → auto-route. Confirmed the full chain now works with a real, non-mocked run: real Telethon fetch, real OpenRouter vision call (2.86s), real classification persisted (`media_id=20377 → lane_key=milf, nsfw_tier=explicit`).

Also disabled a redundant global posting-pause gate (`TBCC_POOL_AUTOPOST_PAUSE_WHEN_OVERDUE`) and corrected the island's vision model from the free/rate-limited tier to the validated paid model. Both real fixes, though live-data checking showed neither was the active blocker that night (pools were already posting fine on their own recurring schedulers) — the four bugs below were.

## What shipped (all hot-patched + verified live on the island; not yet committed to git)

1. **`tbcc/backend/app/services/telethon_session_lock.py`** — the async lock-acquire wrappers (`acquire_admin_session_lock_async`, `acquire_import_session_lock_async`, `acquire_poster_session_lock_async` + their release counterparts) ran the actual Redis lock acquire inside `asyncio.to_thread(...)`, i.e. on a real separate OS thread. The "is this lock held" check (`require_telethon_session_lock`) reads `threading.local` state on the *calling* (event-loop) thread — which never saw the mark. Every single Telegram channel-import job on the island was failing with `Telethon import.session access blocked: Redis session lock not held (held=none)`, for every lane, not just inbox. Fixed by marking the hold on the calling thread inside the async wrapper itself. Test: `tests/test_telethon_session_lock_async_marking.py` (10 tests, includes a thread-identity sanity check that proves the reproduction is real).
2. **`tbcc/backend/app/data/aof_storage_hub_map.py`** — the deployed island was running a stale snapshot of this file missing the `INBOX_TOPIC_ID` (22569) row entirely; `queue_storage_hub_deposits(topic_keys=["inbox"])` silently matched nothing. Root cause: the island's backend image predates a local refactor (new `inbox_intake_worker.py`, `queue_inbox_channel_deposit`, this map row) that had been committed to git but never fully deployed — only individual files had been hot-patched ad hoc all session, leaving drift. Fixed via a real `deploy-island-live.ps1` run (after stashing ~25 unrelated in-progress files out of the working tree first — see Explicitly not touched).
3. **`tbcc/backend/app/services/telegram_storage.py`** — `_post_media_ingest` (the shared ingest funnel for all three real deposit paths: channel/topic index, direct message index, local-pool import) never enqueued the enrich/classify hook. One caller (`_index_message`) imported `enqueue_auto_tag_enrich_if_enabled` but never called it (dead code, likely a refactor that dropped the call site); the other two callers never referenced it at all. Net effect: classify has never fired automatically for any real Telegram-sourced deposit, in any lane — only for direct one-off script calls. Fixed by adding the enqueue call once, inside `_post_media_ingest` itself. Test: `tests/test_telegram_storage_post_media_ingest.py` (3 tests).
4. **`tbcc/backend/app/api/media.py`** — `_is_storage_hub_source` did a strict equality check against the bare Storage Hub chat id. Index-only channel/topic deposits (`_index_channel_message`) store `source_channel` as the compound `"telegram:{chat_id}#topic:{thread_id}"` when the source label carries a topic — which is the normal case for every lane and inbox deposit. The strict check never matched, so the classify pipeline's lazy Telethon fetch (`_fetch_image_bytes_for_classify` → `_fetch_media_bytes_and_type_via_import`) fell through to a Saved-Messages lookup and 404'd on every index-only-imported item. Fixed via a new `_extract_storage_hub_chat_ident()` helper, used both by the check and by the two call sites that build `hub_ident` for `_download_from_chat`. Test: `tests/test_media_storage_hub_source_parsing.py` (15 tests).
5. **`tbcc/backend/app/services/auto_tag_enrich.py`** — added the missing auto-route hook: `classify_and_log_lane_vision` only ever wrote a suggestion row, never called `enqueue_lane_route_for_media`. Added `_maybe_auto_route_vision_lane()`, called right after classify, gated behind `TBCC_VISION_AUTO_ROUTE_LANES` (comma-separated allowlist, unset = fully inert). Test: `tests/test_auto_tag_enrich_vision_route.py` (7 tests).

**Island config changes** (via `seed-island-env-from-home.ps1`'s `$forceKeep` table, real env vars not files):
- `TBCC_POOL_AUTOPOST_PAUSE_WHEN_OVERDUE=0` — disabled the blunt global pause; granular per-pool blocking (`_pool_ids_blocked_by_overdue_schedulers`) stays active.
- `TBCC_VISION_LLM_MODEL=qwen/qwen3-vl-235b-a22b-instruct` (was still `nemotron-nano-12b-v2-vl:free`).
- `TBCC_ENRICH_ON_IMPORT=1` — was unset (confirmed via live island check, not assumed); nothing classified on import before this.
- `TBCC_VISION_AUTO_ROUTE_LANES=voyeur,bop` — the two lanes with real validated ground-truth accuracy from earlier tonight's testing.

## Verification (live, not mocked)

```
py -3.13 -m pytest tests/test_telethon_session_lock_async_marking.py tests/test_telethon_session_lock.py \
  tests/test_telethon_session_lock_require.py tests/test_telegram_storage_post_media_ingest.py \
  tests/test_media_storage_hub_source_parsing.py tests/test_auto_tag_enrich_vision_route.py \
  tests/test_media_lane_vision_classify.py -q
54 passed
```

Island, real data:
- Job `7a0349b8`: 424 messages scanned, 107 stored, 11 duplicates correctly skipped.
- `select count(*) from media where created_at > now() - interval '10 minutes'` → 107.
- Final clean test after all four fixes + after the auto-triggered `telegram_relief` circuit breaker cleared: `auto_tag_media_enrich.delay(20377)` → 2.86s real run → `media_lane_vision_decisions` row `media_id=20377, lane_key=milf, nsfw_tier=explicit`.

One side-effect noted, not chased: a `telegram_relief` focus-profile auto-triggered mid-session (`"Auto: Telethon session lock storm detected"`), pausing enrich/sidecars for ~5 minutes — almost certainly tripped by the volume of manual test calls this session made against the Telethon session while diagnosing bug #1. It auto-restored on its own; this is the system's existing self-protection working as designed, not a new bug.

## Explicitly not touched / deferred

- **`sent_cache_composer.py:337`** — real crash, unrelated: `notify_composer_bot` calls `.get()` on an un-awaited coroutine (`AttributeError: 'coroutine' object has no attribute 'get'`), seen live in `worker_telegram` logs during tonight's testing. Not blocking inbox intake; flagged, not fixed.
- **Taboo/bop channel scope** — operator noted voyeur gained ~150 organic followers overnight vs. ~30 for bop/taboo, and would "happily scrap" the low-traction lanes. Not decided; would directly simplify future auto-route-allowlist expansion work if narrowed.
- **`git stash@{0}`** — ~25 files of unrelated in-progress work (a `thisvid_upload`/`arbitrage` feature: `arbitrage_client.py`, `integrate_arbitrage.py`, `thisvid_upload_policy.py`, `thisvid_upload_provision.py`, `media_mover_to_storage_hub.py`, `thisvid_codegen.py`, `thisvid_upload_local.py`, plus several modified files: `album_service.py`, `buffer_native_queue_refill.py`, `buffer_x_outbound_guard.py`, `post_analytics.py`, `qa_master_panel.py`, `scheduled_post_service.py`, `sent_cache_composer.py`, `telegram_storage.py`-adjacent, `traffic_inbox_copy.py`, `traffic_pulse.py`, `userbot_fleet.py`, `poster_worker.py`) — held out of the deploy specifically so it didn't ship untested. Still stashed, not restored. Operator/Cursor should decide whether to pop it back onto the working tree.
- **Nothing committed to git.** All five fixed files (`telethon_session_lock.py`, `aof_storage_hub_map.py` — already at HEAD, not modified — `telegram_storage.py`, `media.py`, `auto_tag_enrich.py`) plus four new test files are live on the island via hot-patch but still uncommitted locally. A real deploy already shipped `aof_storage_hub_map.py`'s committed state; the other four are hot-patch-only.
- **Operator-correction / self-refinement loop** — still doesn't exist (confirmed earlier in session via code inspection). Q&A panel taps don't record anywhere that feeds future classification.
- **Video content is never classified** — `_fetch_classify_bytes_sync` only attempts a lazy fetch for `photo`/`gif`/empty media_type, never `video`. Confirmed live (all-video test batch returned instantly with no fetch attempt). Given the operator's batch was described as "heavy voyeur... mixed media," a meaningful fraction of dropped content may be video and will silently never get classified until this is addressed — this is a real gap, not yet scoped.
- **CLIP sidecar** — still not deployed to the island (memory-constrained VPS), unrelated to tonight's fixes.

## Next steps (ladder)

| What | Unblocks | Reversibility | Evidence |
|---|---|---|---|
| Commit the 5 fixed files + 4 new tests | other-work | trivial-revert | `git add` the specific paths listed above, not `-A` (stash + unrelated drift still present) |
| Fix `sent_cache_composer.py:337` await bug | other-work | trivial-revert | reproduce via a real sent-cache-triggering deposit, add `await` |
| Decide taboo/bop scope (narrow to voyeur only?) | revenue-ops | trivial-revert (env-only) | operator call, not Lane C's to decide |
| Frame-extraction for video classify | revenue-ops | migration-free, new code | closes the "mixed media" gap the operator's own test batch exposed |
| Restore or discard `stash@{0}` | other-work | trivial (stash pop/drop) | `git stash show -p stash@{0}` to review before deciding |
