# Storage drain + simplest possible controls — Phase 0 report

**Reverse report for forward directive** `tbcc/docs/handoffs/2026-09-03_storage-drain-one-panel.md`
**Executed by:** Claude Code `/cc-run`, 2026-09-03
**Phase:** 0 (clinical inventory — no behavior change) — **STOP for Cursor `/cc-report` ACK**. Phase 1 not started.

---

## Summary

No code changed. This is a read-only inventory of every Storage Hub / Q&A / intake control surface, the deposit/auto-pipe/flush mechanisms behind them, and a locked IA + drain-loop proposal for Phase 1+ to implement without guessing. Literal one-panel is **not realistic** given Telegram's forum-topic structure and the in-context lane workflow — see rationale below. Two duplicate button pairs were found firing the **exact same Celery task** from two different bots.

---

## I1 — No "drain until unique-empty" exists today

**Evidence, exact functions:**
- `storage_auto_pipe.py` `run_lane_auto_pipe()` — one debounced call to `queue_storage_topic_deposit(..., limit=auto_pipe_batch_size(key), ...)`. Single shot.
- `qa_master_panel.py` `queue_lane_deposit_from_master()` — one call to `queue_storage_topic_deposit(..., limit=get_deposit_limit(), sent_cache=False, auto_pipe=False, ...)`. Single shot.
- `hub_lane_control.py` "📥 Deposit now" button → same single-shot deposit, per-lane preset.
- `storage_topic_deposit.py` `queue_storage_topic_deposit()` itself creates exactly **one** `ImportJob` for up to `limit` (capped 200 via `resolve_deposit_limit`) newest-first deduped items, then returns. It already reports `stored` and `skipped_duplicate` counts in the job result (used by `format_deposit_complete_text`) — the primitive drain needs (know if a batch found anything new) already exists, it's just never looped.

**Conclusion:** every existing trigger — auto-pipe, master-panel lane tap, per-lane "Deposit now" — does exactly one bounded batch. None of them repeat until a batch comes back empty.

---

## I2 — Auto-approve toggle never backfills

**Evidence:** `hub_intake_policy.py` `hub_master_auto_approve_enabled()` is a pure Redis flag read (`REDIS_PREFIX:auto_approve`). It has no side effect beyond being read at deposit time (`qa_review_only = not hub_master_auto_approve_enabled()` in `run_lane_auto_pipe` and `queue_lane_deposit_from_master`). Nothing scans existing `quarantine`-status media when the flag flips. `auto_pipe_destination_label()` just describes current state for the panel text — also no rescan.

**Conclusion:** confirmed exactly as scoped. A drain loop must read the auto-approve flag **per batch** (not snapshot it once at drain start) so toggling mid-drain takes effect on the next batch — this satisfies "toggling before or after a dump must not matter" without any change to `hub_intake_policy.py` itself.

---

## I3 — Surface inventory (every control surface + jobs covered)

| # | Surface | File(s) | Primary buttons (count) | Jobs it exposes |
|---|---------|---------|----------------------|------------------|
| 1 | **Per-lane hub panel** (×11 topics: abg, ai, ass, big_tits, blowjob, bop, full_length, goon, milf, taboo, voyeur) | `app/services/hub_lane_control.py` (`lane_hub_control_keyboard`), `bots/storage_hub_control_handlers.py` | 7 rows / **10 controls**: −/+ count, −/+ type, Deposit now, Auto-pipe toggle (1 of 2 shown), Loot preview toggle (1 of 2 shown), Preview rebundle, Rebundle+partial, Master panel, Refresh, 50/100 presets | One-shot deposit (this lane), per-lane auto-pipe, per-lane Loot preview, rebundle loose→albums, jump to master |
| 2 | **Q&A master panel** (fleet control, 1 topic) | `app/services/qa_master_panel.py` (`qa_master_panel_keyboard`), `bots/qa_master_panel_handlers.py` | 7+ rows / **~17 fixed controls** + up to 6 lane shortcuts/page + pagination: Refresh, Review, Dashboard, Auto-pipe ALL on+off (both always shown), Auto-approve on+off (both always shown), dep −/+, type ◀/▶, presets 5/15/25/50, lane emoji buttons, Flush Q&A, Flush hub, Inbox now, Vault flush | One-shot deposit (any lane, shared preset), global auto-pipe, global auto-approve, quarantine flush (all lanes), hub album flush, inbox-now, vault-staging flush, review handoff |
| 3 | **SENT VAULT panel** (1 topic, permanent archive) | `app/services/sent_cache_control.py` | **7 controls**: Composer ON/OFF, Loot preview ON/OFF, Erome ON/OFF, Preview −/+, Album −/+, Flush vault staging, Refresh | Vault composer toggle, vault-sourced Loot preview toggle, Erome export toggle, preview album cap, vault album chunk size, vault-staging flush |
| 4 | **`/intake` panel** (payment bot, global cadence) | `bots/intake_control_handlers.py` (`intake_control_keyboard`) | 6 rows / **9 controls**: Batch +5/+10/+25, Interval +5m/+15m/+30m, Album +1/+2/+3, Run all due lanes, Inbox now, Flush inbox albums, Flush hub albums, Post vault staging, Auto-pipe toggle | Global intake batch/interval/album cadence, force-run due lanes, inbox-now, inbox quarantine album flush, hub album flush, vault-staging flush, global auto-pipe |
| 5 | **`/review`** (quarantine bulk-approve) | `app/services/gatekeeper_review.py` + review keyboard | Waiting count, per-lane filter, Approve/confirm | Bulk-approve quarantine → pool |

**Literal duplicates found (same underlying Celery task, two different buttons on two different bots):**
- `qmp:flush:hub` (Q&A master "📦 Flush hub") and `intake:flush:hub` ("📦 Flush hub albums") both call `flush_storage_hub_album_buffers_task.delay(force=True)` — identical job, different label, different surface.
- `qmp:flush:vault` (Q&A master "🗄 Vault flush") and `intake:flush:sentcache` ("📦 Post vault staging") both call `flush_sent_cache_emoji_buffers_task.delay(force=True)` — identical job, different label, different surface.
- `qmp:apall:on/off` (Q&A master "Auto-pipe ALL") and `intake:autopipe:on/off` (`/intake` panel) both read/write the same `storage_auto_pipe_enabled()` / `set_storage_auto_pipe_enabled()` flag — same global toggle exposed on two bots.
- `qmp:run:inbox` and `intake:run:inbox` both trigger the same inbox-now pull.

**Correction (found during Phase 1 implementation, see below):** the per-lane panel's count/type controls and the Q&A master's dep count/type controls are **not** two independent knobs as originally stated here — both panels import and call the exact same `storage_deposit_control.py` functions (`get_deposit_limit`, `get_deposit_media_types`), a single shared Redis-backed setting rendered on two panels. Not a duplicate-knob problem; no action needed.

---

## I4 — Control sprawl on the primary surfaces

The Q&A master panel alone renders **~17 fixed controls in 7 rows** before any lane shortcuts, pagination, or the flush/inbox/vault row — for what the operator actually does most often (drain a lane, check global toggles). The per-lane panel renders **10 controls per topic × 11 topics**. Both panels currently show **both states of a toggle simultaneously** (`Auto-pipe ALL` ON *and* OFF buttons, `Auto-approve` ON *and* OFF buttons) rather than the single-context-button pattern the per-lane panel *already* uses correctly for its own Auto-pipe/Loot-preview toggles (only the "turn it the other way" button is shown). That inconsistency alone would cut 2 buttons from the master panel's home row for free.

---

## I5 — Flush is opaque and mixed with primary controls

Confirmed via I3's duplicate-task findings above: "Flush Q&A", "Flush hub"/"Flush hub albums", "Vault flush"/"Post vault staging", "Flush inbox albums" are five buttons across two surfaces implementing effectively **three** distinct jobs (quarantine-buffer flush, hub-album-buffer flush, vault-staging flush) plus one inbox-specific flush, all sitting on home rows next to Refresh/Review/Deposit. None of them are the operator's primary drain job — they're "force-post whatever's half-buffered right now" actions, correctly described by the directive as advanced.

---

## I6 — Approve crash on duplicate-in-target-pool

**Evidence, exact lines:** `gatekeeper_review.py` `operator_approve_media()` — line 411 `media.status = "approved"`, line 418 `media.pool_id = int(pid)`, line 420 `db.commit()`. No `try/except` around the commit. If `Media` already has a row with the same `(file_unique_id, pool_id)` pair in the target pool (`uq_media_file_unique_id_pool_id`), this commit raises an uncaught `IntegrityError`/`UniqueViolation`, surfacing as a raw error card to the operator instead of a graceful "already there, treated as done." Operator screenshot 2026-09-03, `pool_id=3`, matches this exact path. **Fixed in Phase 1 — see below.**

---

## I7 — Inbox quarantine flushes 1-by-1

**Evidence:** `inbox_intake_review.py` has **two separate functions**, not one bug:
- `queue_inbox_quarantine_media()` (line 89): `album_size = 1` **hardcoded**, with an explicit comment explaining why — "Inbox cards must appear after a single drop (Inbox now), not wait for 5." This is the auto-flush-on-every-new-item trigger.
- `flush_pending_inbox_quarantine()` (line 100-119): already uses the *configurable* `get_album_size()` for a force/manual flush of whatever's pending.

**Nuance for Phase 2:** the directive's proposed fix (switch the default trigger to `review_batch_size()`, default 10) is about changing the **first** function's hardcoded `1`, not removing the second manual-flush path — "Inbox now" as an instant single-card action was a deliberate choice, not an oversight, so Phase 2 should keep a manual "flush now regardless of batch" override alongside the larger default batch, matching the directive's own acceptance criterion ("partial flush remains a deliberate extras action").

---

## Proposed locked IA (for Phase 1+ — Phase 0 lock, unchanged)

### Why not literal one panel

A Telegram control-panel message lives in exactly one forum topic. Operators use the per-lane panel **in-context** while scrolling that lane's own media (no topic-switch needed to deposit/drain what they're looking at) — collapsing that into the master panel would force a topic switch for the single most common action. Telegram's own structure (11 independent lane topics + 1 fleet topic + 1 vault topic) makes a strict single message impossible without hurting that workflow. **Verdict: 2 primary surfaces, not 1** — per-lane (in-context) and master (fleet) — plus one shared Extras destination reachable from both, replacing the third+fourth+fifth surfaces (SENT VAULT panel's unique controls, `/intake`'s unique controls, and all the flush buttons) rather than keeping them as independent peers.

### Home — per-lane panel (≤6 primary buttons, was 10)

| Button | Replaces |
|--------|----------|
| **🚿 Drain this lane** | "📥 Deposit now" — same button, loops until a batch stores 0 new uniques or hits the safety cap (see drain loop below) |
| **⏸/▶ Auto-pipe** (single context button, already correct) | unchanged |
| **🔄 Refresh** | unchanged |
| **🟡 Master panel** | unchanged |
| **⋯ More** | new — opens Extras: count/type fine-tune, 50/100 presets, Loot preview toggle, Preview rebundle, Rebundle+partial |

### Home — Q&A master panel (≤8 primary buttons, was ~17)

| Button | Replaces |
|--------|----------|
| **🔄 Refresh** | unchanged |
| **🚿 Drain lane** (paginated shortcuts, same lane-picker UX as today) | today's one-shot "dep:{lane}" buttons |
| **⏸/▶ Auto-pipe ALL** (single context button) | today's always-both apall:on + apall:off |
| **⏸/▶ Auto-approve** (single context button) | today's always-both aapr:on + aapr:off |
| **📋 Review** | unchanged |
| **⋯ More** | new — opens Extras: Dashboard link, dep count/type/presets, Flush Q&A, Flush hub *(single button — was duplicated with `/intake`)*, Vault flush *(single button — was duplicated as "Post vault staging")*, Inbox now |

### Extras (shared destination, reached from either home surface)

One panel (or a short message with its own keyboard) holding everything that isn't the daily drain/toggle loop: deposit count/type fine-tune + presets, the three real flush jobs (quarantine / hub-album / vault-staging — each now a **single** button instead of duplicated across two bots), rebundle preview/run, dashboard link, SENT VAULT's composer/Erome/preview-cap settings, and `/intake`'s batch/interval/album cadence knobs. `/intake` and the SENT VAULT panel stop being independent peers — their unique settings move here; their duplicated actions (flush-hub, flush-vault, auto-pipe toggle, inbox-now) are deleted, not kept as a second copy.

**Simplicity accounting:** 5 conceptually-independent surfaces (lane×11, master, vault, intake, review) collapse to 2 primary shapes (lane-local, master) + 1 shared extras — the physical per-lane message count stays at 11 (a Telegram constraint, not a design failure) but the *distinct control vocabulary* an operator has to remember drops from ~5 overlapping sets to 2 small home rows plus one common "everything else" page.

---

## Phase 0 verification (no behavior change)

```
git diff --stat  →  (no output; this report is the only new file)
```
No panel, deposit, or auto-pipe runtime path was edited in Phase 0. All findings above were read-only citations of existing code.

---

## Phase 1 (drain loop + duplicate-safe approve) — implemented, ACK'd Phase 0 → Phase 1 authorized

**Executed by:** Claude Code `/cc-run`, 2026-09-03 (continuation of this same track). **STOP for Cursor `/cc-report` ACK.** Phase 2 not started.

### I1 — Drain-this-lane implemented

**New:** `app/services/storage_lane_drain.py` — loops the existing `queue_storage_topic_deposit` + `await_deposit_import_job` primitives (no second import stack, per constraint). Per-lane exclusivity via a Redis lock (`tbcc:storage:drain:lock:{lane}`), same pattern as `storage_auto_pipe.py`'s pending-task key. `start_lane_drain()` (sync trigger, acquires lock + posts a status message + enqueues the Celery task), `run_lane_drain()` (the async loop, called from the task), `cancel_lane_drain()` / `is_lane_draining()`.

**New:** `app/workers/storage_lane_drain_worker.py` — `run_lane_drain_task` Celery task, `asyncio.run(run_lane_drain(...))`, matching the existing `asyncio.run()`-per-task pattern used across `poster_worker.py`.

**Cursor lock honored exactly:** stop condition is `stored == 0 AND skipped_duplicate == 0` for a batch — **not** `stored == 0` alone. A batch with `stored=0, skipped_duplicate>0` continues looping (newest-first can sit on an already-indexed head while older uniques remain further back). Covered by `test_drain_continues_past_stored_zero_when_skipped_positive`.

**Other locks honored:**
- `hub_master_auto_approve_enabled()` is re-read **every batch** (not snapshotted at drain start) — `test_drain_reads_auto_approve_fresh_each_batch` proves batch N and batch N+1 can see different `qa_review_only` values.
- `sent_cache=False` and `auto_pipe=False` passed explicitly on every batch (never inherited from a global default) — `test_drain_always_passes_sent_cache_false`.
- Safety cap: `TBCC_LANE_DRAIN_MAX_ITERATIONS` (default 40) and `TBCC_LANE_DRAIN_MAX_SECONDS` (default 1800) — whichever fires first, reported as `stop_reason` (`safety_cap_iterations` / `safety_cap_seconds`), never a silent stop.
- Cancel: clearing the Redis lock (`cancel_lane_drain`) is checked at the top of every loop iteration, before the next batch starts — `test_drain_stops_on_cancel`.
- Progress: the same status message is edited each iteration (`storage_hub_op_status.py`'s existing `post_hub_op_status`/`edit_hub_op_status` HTTP helpers — reused, not reinvented) with running totals; a final summary line states which stop condition fired.

**Wired into the per-lane hub panel:** `hub_lane_control.py`'s "📥 Deposit now" button is now "🚿 Drain this lane" (`hubctl:drain`), per the directive's preference to replace rather than add. Handler in `bots/storage_hub_control_handlers.py` calls `start_lane_drain`, with an "already draining" toast if the lock is held. The old one-shot deposit function (`_run_deposit_from_panel`) is untouched, just no longer wired to this button — available for Phase 2's Extras page.

**Deferred (explicitly optional in the directive):** master-panel lane-shortcut wiring to the same drain. Not done this pass — the per-lane panel change alone is a real behavior change touching a live production path; wiring a second entry point before that one has been used live felt like unnecessary added risk for an explicitly-optional item. Recommend doing it in Phase 2 alongside the panel shrink, once the per-lane drain button has been exercised for real.

### I6 — Duplicate-safe approve implemented

`gatekeeper_review.py` `operator_approve_media()` now wraps the commit: on `IntegrityError` matching the `(file_unique_id, pool_id)` unique constraint (checked by both the Postgres constraint name and the SQLite column-name message, via new helper `_is_duplicate_file_unique_id_pool_id_violation` — the two engines report this differently and dev/test runs on SQLite), it rolls back, re-fetches the media row, approves it **without** the conflicting route (`pool_id` left unset rather than force-assigned), and commits again. Any *other* `IntegrityError` still re-raises unchanged — only this specific, known-benign duplicate case is swallowed. The returned dict gains `duplicate_route_skipped: bool` so callers/toasts can say "already there" instead of a generic success.

**Known follow-up nuance (not fixed this pass, out of I6's scope):** when the duplicate path fires, the downstream lane-route enqueue (`enqueue_lane_route_for_media`) and micro-pull triggers still use the originally-*intended* `selected` lanes even though `pool_id` was reset to `None` — a minor inconsistency between "what lane the operator picked" and "what pool_id actually landed." I6's ask was specifically the crash; fixing this downstream nuance would need a clearer read of `enqueue_lane_route_for_media`'s expectations and felt like scope creep for this slice.

### Pytest (directive's exact verification command)

```
cd tbcc/backend && py -3.13 -m pytest tests/test_storage_lane_drain.py tests/test_gatekeeper_approve_duplicate.py -x -q --tb=short
→ 15 passed in 16.36s
```

**Environment finding (not caused by this phase, flagging for awareness):** running `test_gatekeeper_review.py`'s pre-existing `test_operator_approve_sets_status` / `test_operator_approve_enqueues_micro_pull` in isolation (a fresh `pytest` process, e.g. `pytest tests/test_gatekeeper_review.py::test_operator_approve_sets_status` alone) hangs — confirmed independently of any Phase 1 change. Root cause: `operator_approve_media` unconditionally calls `enqueue_vault_approved_media` / `_refresh_qa_live_counter_after_decide`, which do a cold `from app.workers.gatekeeper_review_worker import ...` on first call; that import chain reaches `celery_app.py`, and in this dev/sandbox environment the configured broker isn't reachable in a way that fails fast — it blocks. This only surfaces when those tests run *first* in a fresh process (normal full-suite runs are unaffected because some earlier-alphabetical test file apparently reaches the same import first and it resolves fine bundled with other setup, or the specific ordering here just never isolates those two tests alone). My new `test_gatekeeper_approve_duplicate.py` mocks every one of these `.delay()`-triggering calls precisely to avoid depending on that — good test hygiene regardless, but the pre-existing gap in `test_gatekeeper_review.py` itself is a separate, real latent fragility worth a follow-up (not fixed here — out of I6's scope, and touching a file outside this track's explicit remit).

### Git / deploy

7 files touched (3 modified, 4 new) — under the 8-file halt threshold:
- `app/services/storage_lane_drain.py` (new)
- `app/workers/storage_lane_drain_worker.py` (new)
- `app/services/hub_lane_control.py` (modified — button swap)
- `bots/storage_hub_control_handlers.py` (modified — handler swap)
- `app/services/gatekeeper_review.py` (modified — I6 fix)
- `tests/test_storage_lane_drain.py` (new)
- `tests/test_gatekeeper_approve_duplicate.py` (new)

**No island deploy, no bot start, no `.env`/session changes** — matches the directive's explicit out-of-scope list. This is a code-only slice; the drain button will only go live once this deploys, which is a separate authorized action (not implied by this report).

**Completion gates:**
| Gate | Result |
|------|--------|
| Tests | pass — 15/15 for the directive's exact verification command |
| Migration | N/A — no schema change (the unique constraint already existed) |
| Stack | N/A — no deploy, no restart, no bot spawn this phase |
| Extension version | N/A |
| Git | 1 commit pending (this report + the 6 code/test files) |
| Scope | 7 files — under the 8-file halt threshold |

---

## Phase 1b (celery wire-up — ship gate) — implemented, ACK'd Phase 1 → 1b authorized

**Executed by:** Claude Code `/cc-run`, 2026-09-03 (continuation). **STOP for Cursor `/cc-report` ACK.** Phase 2 not started. No island deploy performed — Cursor authorizes that separately after this ACK.

**Gap Cursor caught:** `app.workers.storage_lane_drain_worker` (new in Phase 1) was never added to `celery.conf.include` in `app/workers/celery_app.py`, and had no `task_routes` entry. The "Drain this lane" button would successfully call `.delay(...)` (Celery doesn't validate task existence at enqueue time), but no running worker process imports that module, so the task would sit unconsumed in the queue forever — a silent no-op from the operator's perspective, not a crash. Correctly caught before any deploy.

**Fix, mirrors `storage_auto_pipe_worker` exactly (same job class — Telethon-backed lane deposit):**
- `celery_app.py` `conf.include`: added `"app.workers.storage_lane_drain_worker"` immediately after `storage_auto_pipe_worker`'s entry.
- `celery_app.py` `conf.task_routes`: added `"app.workers.storage_lane_drain_worker.*": {"queue": "telegram"}` immediately after `storage_auto_pipe_worker`'s route, same `telegram` queue (drain uses the identical Telethon deposit primitive, so it belongs on the same queue for the same reason auto-pipe does).

**Test:** extended the existing `test_celery_island_beat_gates.py` (which already had this exact assertion shape for `network_liveness_worker`/`storage_auto_pipe_worker`) with `test_storage_lane_drain_worker_is_included_and_registered` — checks `include`, `task_routes`, **and** that the task name (`app.workers.storage_lane_drain_worker.run_lane_drain`) is actually present in `celery.tasks` after import, which is the real "would a worker recognize this" signal (stronger than just checking `include`, which only proves the module *would* get imported on worker startup, not that it exports the expected task name).

### Verification (directive's exact commands)

```
py -3.13 -c "from app.workers.celery_app import celery; assert 'app.workers.storage_lane_drain_worker' in (celery.conf.include or [])"
→ passes (no AssertionError)

py -3.13 -m pytest tests/test_storage_lane_drain.py tests/test_gatekeeper_approve_duplicate.py -x -q --tb=short
→ 15 passed

py -3.13 -m pytest tests/test_celery_island_beat_gates.py -x -q --tb=short
→ 5 passed (new registration test included)
```

### Git

1 file modified (`celery_app.py`) + 1 file modified (`test_celery_island_beat_gates.py`) = 2 files, well under the 8-file threshold.

**Completion gates:**
| Gate | Result |
|------|--------|
| Tests | pass — 20/20 combined (15 Phase 1 + 5 celery registration) |
| Migration | N/A |
| Stack | N/A — config-only change, no restart/deploy performed this phase |
| Extension version | N/A |
| Git | 1 commit pending |
| Scope | 2 files |

**Island deploy is still pending** — this phase only fixes the code; the running island `worker`/`worker_post` containers need the updated `celery_app.py` to actually pick up the include/route before "Drain this lane" works live. That deploy is explicitly Cursor's call per the directive ("Island deploy — Cursor authorizes separately after 1b").

---

## Not done / next

**Before Phase 2:** island deploy of the Phase 1 + 1b code (drain loop, I6 fix, celery wire-up) — not performed this pass, awaiting Cursor authorization.
**Phase 2 (needs Cursor ACK):** shrink both home panels to the button lists locked in Phase 0, stand up the shared Extras destination, delete the four duplicate buttons identified in I3/I5, restore inbox batch to `review_batch_size()` default (I7) while keeping the manual instant-flush override, wire the optional master-panel drain shortcut deferred from Phase 1.
**Phase 3 (optional, after Phase 2 ACK):** soft-deprecate `/intake` and per-lane flush chrome that's now redundant with Extras; update `STORAGE_HUB_PANEL_MANUAL.md` to match (it still documents "📥 Deposit now" on the lane panel — needs a line change once this deploys).
**Follow-up, no phase assigned yet:** the pre-existing Celery cold-import test isolation gap in `test_gatekeeper_review.py` (see Phase 1 section above) — worth a small fix (mock the same three calls) but outside this track's scope.

---

**Phase 1b done — STOP for Cursor `/cc-report`. Do not start Phase 2. No island deploy performed.**
