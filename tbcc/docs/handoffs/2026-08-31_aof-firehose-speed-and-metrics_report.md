# Report: AOF firehose — sub-5s per item + honest hub metrics

## Addendum — Cursor `/cc-report` review response (2026-08-31)

Cursor's `/cc-report` verdict: **wait** — code correct and committed, but I1 unproven live (bench needs fresh un-uploaded files + operator's running stack) and gap #5 flagged the bench script requiring `PYTHONPATH=.` to run.

**Fixed here (code-only, no local stack touched):** `bench_aof_firehose.py` was missing the `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` fixup every other script in `tbcc/backend/scripts/` uses — without it, `from app.services...` only resolves if the caller manually sets `PYTHONPATH`. Added the same fixup; `py -3.13 scripts/bench_aof_firehose.py --help` now runs standalone from `tbcc/backend` with no env var needed, matching the usage line already in the script's docstring. Re-ran the full verification set (28 tests) after the change — unaffected, all green.

**Not done here — operator/Cursor-side per the review's own framing ("Operator next (Tray / local only)") and this session's Operator policy (no local daemon start/stop, no `.env` edits, no stack restarts from Claude Code):**
- Restarting the local API / watch organizer / lane-hub daemons so the running processes pick up commit `b007594`.
- Adding `TBCC_WATCH_AOF_FAST=1` + the two batch-size knobs to `tbcc/.env`.
- Running the bench against fresh (not-yet-ledgered) files for a real `median_seconds_per_upload=`.
- Gap #6 (live watchdog debounce path still single-file-per-connect) — noted, deliberately left as-is; batching the live debounced stream (as opposed to the startup backlog scan already fixed) risks introducing race conditions between independent per-file debounce timers for a case that wasn't the operator's reported failure (181-backlog, not live trickle). Flagging as a Phase 2 candidate rather than folding it in unreviewed.

## Phase 1 — Speed + honest metrics + tests (2026-08-31)

**Against:** `tbcc/docs/handoffs/2026-08-31_aof-firehose-speed-and-metrics.md`, "ACTIVE for /cc-run — Phase 1" block
**Session:** cold-start via `/cc-run` — read `CURRENT_DIRECTIVE.md` + this file's Phase 1 block; no other prior chat used

## Summary

Read the code cold before touching anything. Three of the six P0/P1 issues had a single, findable root cause each; the other three were straightforward gaps. Fixed all six (I1 is the emergent result of I4+I5+I6, not a separate code change):

- **I4 (root cause found):** `telethon_disconnect_import_after_io()` in `app/utils/telethon_session.py` unconditionally returns `True` on Windows (`if os.name == "nt": return True`) — a deliberate anti-lock-storm guard for Celery+uvicorn contention. Every `deposit_local_file()` call did its own `asyncio.run()` → `run_telegram_import_io()`, so that guard disconnected the Telethon session at the end of **every single upload**. That's the "connect/disconnect every upload" pattern in the logs (~20–40s/upload). Left the guard itself untouched (it's load-bearing for concurrent API/Celery access) and instead gave the lane-hub backlog scan a way to hold one session open across many files.
- **I5 (confirmed + fixed):** `deposit_local_file()` did `_sha256_file(path)` (a full streamed read) and then, separately, `path.read_bytes()` (a second full read) for every uploaded file. Now reads the file once and hashes the in-memory bytes.
- **I2 (root cause found):** `WatchFolder.tsx`'s "Storage Hub uploads (ledger)" bar computed `width: 20 + hubTotal * 5` — a formula with no relationship to a pending count, capped at 100% once `hubTotal ≥ 16`. At ledger=33 it was already pinned at 100% green regardless of the 181-image backlog. This is the literal false-green bug the operator saw.
- **I3 (gap, not a bug):** `aof_network_monitor.py`'s `summary` had `hub_uploads_total` (all-time ledger count) but nothing representing "still on disk, not yet uploaded." Files are **never deleted** after upload (ledger dedupes by path+hash; it doesn't move/clear the source), so disk media-count alone can never signal drain — that's why "181 never decreased" independent of actual upload progress.

## Done

- **I4 / I1 — `local_lane_hub_deposit.py`:** split `deposit_local_file()` into a disk-only prep step (`_prepare_deposit`) and an upload step (`_do_upload`, `_finalize_upload_result`). Added `deposit_local_files_batch(paths, ...)` which preps every file locally, then uploads all pending items through **one** `run_telegram_import_io()` call (`_upload_pending_batch`) — one Telethon connect/disconnect for the whole batch instead of one per file. `deposit_local_file()` is kept as a single-file convenience wrapper (used by the live watchdog debounce path, unchanged). Added `_chunk_paths_for_batch()` to cap each session's batch by count (`TBCC_LOCAL_LANE_HUB_BATCH_SIZE`, default 10) and total bytes (`TBCC_LOCAL_LANE_HUB_BATCH_MAX_BYTES`, default 200MB) so a backlog of large videos can't balloon memory. `scan_lane_folders_once()` (the startup backlog scan — this is what runs against the operator's 181-image queue) now chunks each lane's files through the batch path instead of calling `deposit_local_file()` per entry.
- **I5 — `local_lane_hub_deposit.py`:** removed `_sha256_file()`; `_prepare_deposit()` now does `raw = path.read_bytes()` once and `hashlib.sha256(raw).hexdigest()` from the in-memory bytes. The pre-existing path+mtime+size ledger fast-skip (zero-read on a repeat scan hit) was already correct and is unchanged.
- **I2 — `WatchFolder.tsx` + `api.ts`:** replaced the fake `20 + hubTotal*5` bar with a real "Storage Hub queue" bar driven by the new `hub_pending_uploads` field — `uploaded/(uploaded+pending)` width, green only when `pending === 0`, amber/cyan while draining. StageCard #3 now shows `uploaded/total` with a "pending" label instead of a bare ledger count. Added a "Hub pending" stat tile and per-lane pending counts in `LaneRow`. Added `pending_uploads?: number | null` to `AofNetworkLane` and `hub_pending_uploads?: number | null` to the `summary` type in `api.ts`.
- **I3 — `aof_network_monitor.py`:** each lane now computes `pending_uploads = max(0, media_count - ledger_uploads_for_that_lane)` (clamped so a file deleted post-upload can't push it negative), summed into `summary.hub_pending_uploads`. Reuses the existing per-lane `by_lane` ledger breakdown — no new DB query, no path-prefix matching needed since each lane folder maps 1:1 to a `network_key`.
- **I6 — `watch_folder_aof.py` (`watch_aof_fast_mode()`), `watch_folder_organizer.py`, `local_lane_hub_worker.py`:** new `TBCC_WATCH_AOF_FAST=1` flag. When set, watch-organizer and lane-hub debounce/stable waits are clamped to ≤0.5s (`min(configured, 0.5)`) in both the daemon and `--once` scan paths, regardless of the individual `*_DEBOUNCE_S`/`*_STABLE_WAIT_S` values in `.env`.
- **I8 — `watch_folder_aof.py`:** `preprocess_inbox_media()` skips the `watermark_file()` call entirely when `watch_aof_fast_mode()` is on (sets `watermark_skipped: "fast_mode"` in the sidecar meta instead). AOF rename still runs — it's a cheap local `os.rename`, not the expensive part.
- **Tests (6 new, `tbcc/backend/tests/`):**
  - `test_local_lane_hub_deposit.py::test_batch_upload_reuses_single_telethon_session` — asserts a 5-file batch opens exactly **1** Telethon session (I4's acceptance criterion, ≥10 in the real batch-size default).
  - `test_local_lane_hub_deposit.py::test_deposit_reads_file_bytes_once` — asserts `Path.read_bytes` is called exactly once per upload (I5).
  - `test_local_lane_hub_deposit.py::test_chunk_paths_for_batch_respects_count_cap` / `test_chunk_paths_for_batch_respects_byte_cap` — chunking math.
  - `test_aof_network_monitor.py::test_hub_pending_uploads_reflects_disk_minus_ledger` / `test_hub_pending_uploads_never_negative` — I3's metrics math, including the clamp.
  - `test_watch_folder_aof_lanes.py::test_fast_mode_skips_watermark` — I8.
- **Bench harness (scope: "optional but preferred") — `tbcc/backend/scripts/bench_aof_firehose.py`:** times N real uploads from a given lane through `deposit_local_files_batch`, wrapping `_do_upload` with a stopwatch to report a true per-item median (not just batch-wall/N) even though the whole run shares one session. Prints `median_seconds_per_upload=` and PASS/FAIL against the 5.0s target. **Not run by this session** — see Not done below.

## Not done / explicitly out of scope this phase

- **I7 (concurrent deposit pool)** — explicitly Phase 2 per the directive's own Phases section ("Phase 2 (after ACK): I7 concurrency"). The batching in I4/I1 above is sequential-per-chunk, not parallel; it wins by amortizing connect overhead across a chunk, not by running chunks concurrently. Left the "Unsorted first" scan ordering as-is (already present pre-directive).
- **`tbcc/.env.example`** — in scope per the directive, but this session's permission settings deny read/write on `tbcc/.env.example` outright (denied even for `Read`). Documenting the new knobs here instead — operator/Cursor should add these to `.env.example` directly:
  ```
  # Local lane-hub firehose — batch a Telethon session across a backlog scan (I4)
  TBCC_LOCAL_LANE_HUB_BATCH_SIZE=10
  TBCC_LOCAL_LANE_HUB_BATCH_MAX_BYTES=209715200
  # Fast hot-path: clamp watch/hub debounce+stable to <=0.5s, skip watermark (I6/I8)
  TBCC_WATCH_AOF_FAST=0
  ```
- **`telegram_admin.py` / `telegram_storage.py`** — listed in the directive's scope, but turned out unnecessary: the existing `run_telegram_import_io()` single-flight/session-reuse machinery already does the right thing once given a job that uploads more than one file per call. I4 was fixed entirely at the `local_lane_hub_deposit.py` call-site level; touching the session-management internals wasn't needed and would have risked the Windows anti-lock-storm guard that other callers (Celery, dashboard thumbnails) depend on.
- **Live bench numbers** — this sandbox has no operator AOF NETWORK folder tree, no `admin.session`/`admin_import.session`, and `.env`/`.env.example` are permission-denied for read, so `bench_aof_firehose.py` cannot be run here (would need real media + a live Telegram session, both operator-machine-only per Operator policy). Did not fabricate numbers. Design-basis reasoning for why this should hit target is in the timing table below; operator or Cursor should run the bench command and paste the real output before this is called closed.

## Files touched this phase

**New (untracked, part of Phase 1):**
- `tbcc/backend/app/services/local_lane_hub_deposit.py` — 532 lines (prep/upload split, batching, single-read hash)
- `tbcc/backend/app/services/local_lane_hub_worker.py` — 205 lines (fast-mode debounce/stable clamp, 2 call sites)
- `tbcc/backend/app/services/aof_network_monitor.py` — 403 lines (`pending_uploads` per lane, `hub_pending_uploads` summary field)
- `tbcc/backend/scripts/bench_aof_firehose.py` — new, 93 lines
- `tbcc/backend/tests/test_local_lane_hub_deposit.py` — new tests appended, 227 lines total
- `tbcc/backend/tests/test_aof_network_monitor.py` — new tests appended, 102 lines total

*(These 3 services + worker were already present but uncommitted from the prior Cursor session per this directive's "Prior state" — `git status` shows them `??` untracked, not `M`. This phase edited them in place.)*

**Modified (already had uncommitted diff from the prior Cursor session before this phase started):**
- `tbcc/backend/app/services/watch_folder_aof.py` — this phase's delta: `watch_aof_fast_mode()` + watermark-skip gate (~20 lines)
- `tbcc/backend/app/services/watch_folder_organizer.py` — this phase's delta: fast-mode debounce/stable clamp in `main()` (~5 lines)
- `tbcc/backend/tests/test_watch_folder_aof_lanes.py` — this phase's delta: +1 test, 26 lines
- `tbcc/dashboard/src/api.ts` — this phase's delta: 2 new optional fields (`pending_uploads`, `hub_pending_uploads`)
- `tbcc/dashboard/src/panels/WatchFolder.tsx` — this phase's delta: honest hub-queue bar + StageCard/LaneRow pending display (~60 lines); the file's full `git diff --stat` (537 lines) is dominated by the prior session's pre-existing uncommitted panel work, not this phase.

Total: 11 files. Flagging per CLAUDE.md's ">8 files modified" gate — all 11 are inside the forward directive's explicit `Scope (in)` list (tests + bench script were explicitly requested there too), so continuing rather than halting; noting it here per that gate's instruction to report pass/skip-with-reason rather than silently proceed.

## Verification

```
cd tbcc/backend
py -3.13 -m pytest tests/test_aof_network_monitor.py tests/test_local_lane_hub_deposit.py tests/test_daemon_process_probe.py -q --tb=short
py -3.13 -m pytest tests/test_watch_folder_aof_lanes.py tests/test_watch_folder_control.py -q --tb=short
```
```
28 passed in 99.25s
```
(23 from the directive's minimum verification set + `test_watch_folder_aof_lanes.py`/`test_watch_folder_control.py` for the I6/I8 changes, all green.)

`py_compile` clean on all 5 touched backend `.py` files + the new bench script. `npx tsc -b --noEmit` on the dashboard shows **no new errors** from `api.ts`/`WatchFolder.tsx` — the one `WatchFolder.tsx` error (`useState` unused, line 1) and ~20 errors across other panels are pre-existing on this branch (confirmed: none are in files this phase touched besides that one pre-existing unused import, which predates this session).

### Bench (not run — see Not done)

```
py -3.13 scripts/bench_aof_firehose.py --count 10 --lane inbox
```
Design-basis expectation vs. the directive's own timing budget table:

| Checkpoint | Before (directive estimate) | After (design basis) |
|------------|------------------------------|------------------------|
| watch debounce+stable | 3.5s | ≤0.5s with `TBCC_WATCH_AOF_FAST=1` |
| watch preprocess/watermark | 0.5–2s | 0 (skipped in fast mode) |
| hub debounce+stable | 4s | ≤0.5s with `TBCC_WATCH_AOF_FAST=1` |
| sha256 + read bytes | 2× file IO | 1× (hash from bytes already read) |
| telethon connect/upload | 15–30s **per file** | ≤3s **amortized** — 1 connect per 10-file batch instead of per file (I4) |
| **end-to-end per image** | **30–60s+** | **design target ≤5s median** — not measured live this session |

## Operator smoke checklist (run the bench for real numbers, not self-reported)

1. `cd tbcc/backend && py -3.13 scripts/bench_aof_firehose.py --count 10 --lane inbox` against the real Unsorted backlog — paste `median_seconds_per_upload=` into the Cursor `/cc-report` thread.
2. Start the lane-hub daemon against the real 181-image backlog (or whatever remains); watch `curl -s "http://127.0.0.1:8000/aof-network/status?fast=true"` — confirm `summary.hub_pending_uploads` starts near the real backlog size and counts down as uploads land, and that the dashboard's "Storage Hub queue" bar stays non-green (cyan/amber) until `hub_pending_uploads` actually hits 0.
3. If bench median is still >5.0s after this phase, that's the trigger for the Phase 2 proposal (I7 concurrent pool / Celery) the Working agreement calls for — not a silent retry of this phase.

## Next steps

| What | Unblocks | Reversibility | Evidence |
|------|----------|----------------|----------|
| Cursor `/cc-report` ACK on this report | Phase 2 (I7 concurrency) or closing the track if bench already ≤5s | trivial-revert (nothing pushed) | this file |
| Operator runs `bench_aof_firehose.py --count 10 --lane inbox` on the real backlog | closes I1's acceptance criterion with real numbers | trivial-revert (upload-only script) | pasted `median_seconds_per_upload=` line |
| Add the two new env knobs to `tbcc/.env.example` (blocked here by permissions) | keeps the fast-path documented for the next operator/session | trivial-revert | `git diff tbcc/.env.example` |
| Phase 2 — I7 concurrent deposit pool, only if bench still >5s | closes SPRINT_STATE.md firehose-speed goal if fast-mode alone isn't enough | migration-free (pure worker-count change) | rerun of the same bench command |
| Commit these 11 files as a focused Phase 1 slice (not the branch's other pre-existing unrelated dirty files) | Cursor review, eventual push | trivial-revert (pre-push) | `git status` shows only these 11 staged |

**STOP** — Phase 1 done. Waiting for Cursor `/cc-report` before Phase 2. Not starting Phase 2 in this session.
