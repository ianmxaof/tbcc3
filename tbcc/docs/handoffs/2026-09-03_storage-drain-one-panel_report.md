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

**Independent-but-overlapping "how much to deposit" knobs:** the per-lane panel's count/type controls (50-200, step 50) and the Q&A master's dep count/type controls (5/15/25/50 presets) are two separately-persisted settings for conceptually the same action (how much to pull this time), scoped differently (per-lane vs shared default) — not a bug, but adds to the "too many things to remember" surface area I4 flags.

---

## I4 — Control sprawl on the primary surfaces

The Q&A master panel alone renders **~17 fixed controls in 7 rows** before any lane shortcuts, pagination, or the flush/inbox/vault row — for what the operator actually does most often (drain a lane, check global toggles). The per-lane panel renders **10 controls per topic × 11 topics**. Both panels currently show **both states of a toggle simultaneously** (`Auto-pipe ALL` ON *and* OFF buttons, `Auto-approve` ON *and* OFF buttons) rather than the single-context-button pattern the per-lane panel *already* uses correctly for its own Auto-pipe/Loot-preview toggles (only the "turn it the other way" button is shown). That inconsistency alone would cut 2 buttons from the master panel's home row for free.

---

## I5 — Flush is opaque and mixed with primary controls

Confirmed via I3's duplicate-task findings above: "Flush Q&A", "Flush hub"/"Flush hub albums", "Vault flush"/"Post vault staging", "Flush inbox albums" are five buttons across two surfaces implementing effectively **three** distinct jobs (quarantine-buffer flush, hub-album-buffer flush, vault-staging flush) plus one inbox-specific flush, all sitting on home rows next to Refresh/Review/Deposit. None of them are the operator's primary drain job — they're "force-post whatever's half-buffered right now" actions, correctly described by the directive as advanced.

---

## I6 — Approve crash on duplicate-in-target-pool

**Evidence, exact lines:** `gatekeeper_review.py` `operator_approve_media()` — line 411 `media.status = "approved"`, line 418 `media.pool_id = int(pid)`, line 420 `db.commit()`. No `try/except` around the commit. If `Media` already has a row with the same `(file_unique_id, pool_id)` pair in the target pool (`uq_media_file_unique_id_pool_id`), this commit raises an uncaught `IntegrityError`/`UniqueViolation`, surfacing as a raw error card to the operator instead of a graceful "already there, treated as done." Operator screenshot 2026-09-03, `pool_id=3`, matches this exact path.

---

## I7 — Inbox quarantine flushes 1-by-1

**Evidence:** `inbox_intake_review.py` has **two separate functions**, not one bug:
- `queue_inbox_quarantine_media()` (line 89): `album_size = 1` **hardcoded**, with an explicit comment explaining why — "Inbox cards must appear after a single drop (Inbox now), not wait for 5." This is the auto-flush-on-every-new-item trigger.
- `flush_pending_inbox_quarantine()` (line 100-119): already uses the *configurable* `get_album_size()` for a force/manual flush of whatever's pending.

**Nuance for Phase 2:** the directive's proposed fix (switch the default trigger to `review_batch_size()`, default 10) is about changing the **first** function's hardcoded `1`, not removing the second manual-flush path — "Inbox now" as an instant single-card action was a deliberate choice, not an oversight, so Phase 2 should keep a manual "flush now regardless of batch" override alongside the larger default batch, matching the directive's own acceptance criterion ("partial flush remains a deliberate extras action").

---

## Proposed locked IA (for Phase 1+ — not implemented this phase)

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

## Drain loop design (for Cursor ACK before Phase 1 implements it)

**Extends existing primitives — no second import stack**, per the directive's constraint:

1. **Trigger:** "🚿 Drain this lane" (lane panel) or a lane shortcut tagged `drain` on the master panel. Acquire a per-lane Redis lock (same pattern as `storage_auto_pipe.py`'s `_pending_task_key`) so a second tap while draining is a no-op with a "already draining" toast, not a second concurrent loop.
2. **Batch size:** reuse `auto_pipe_batch_size(lane_key)` / the lane's own preset (50-200) — no new constant.
3. **Loop body, each iteration:**
   - Re-read `hub_master_auto_approve_enabled()` **fresh** (not snapshotted) → `qa_review_only` for this batch — satisfies I2's "toggle timing must not matter."
   - Call the existing `queue_storage_topic_deposit(..., limit=batch, auto_pipe=False, sent_cache=False, qa_review_only=..., commit=True)` — identical to today's one-shot deposit.
   - `await_deposit_import_job(...)` (existing) until terminal.
   - Read `result["stored"]` and `result["skipped_duplicate"]` from the job (both already returned today).
4. **Stop conditions (first one hit wins):**
   - `stored == 0` for an iteration → lane is unique-drained; report "drained, N total stored across M batches."
   - Safety cap: iteration count (e.g. 40) or wall-clock (e.g. 30 min), whichever first → report "safety cap hit, N stored so far, tap Drain again to continue" (never silently stop without saying why).
   - Operator sends a cancel action (reuse the lock key as the cancel switch — clearing it mid-loop stops the next iteration from starting).
5. **Progress:** edit the same in-topic message each iteration (reuse `run_deposit_subtopic_followup`'s heartbeat/edit pattern) — running total stored, iteration count, current stage — not one message per batch.
6. **Concurrency:** one drain per lane at a time (the lock above); no cross-lane limit needed since `queue_storage_topic_deposit` already serializes through the same Telethon/Celery import path every deposit uses today.
7. **Duplicate handling (I6):** Phase 1 should also wrap `operator_approve_media`'s commit in a try/except that treats the specific `uq_media_file_unique_id_pool_id` violation as "already approved, skip" rather than a red error card — small, isolated fix, same phase as drain since both touch the same "don't error on a duplicate" theme.

---

## Verification (Phase 0 — no behavior change)

```
git diff --stat  →  (no output; this report is the only new file)
```
No panel, deposit, or auto-pipe runtime path was edited. All findings above are read-only citations of existing code.

**Completion gates:**
| Gate | Result |
|------|--------|
| Tests | N/A — no code touched |
| Migration | N/A |
| Stack | N/A — no restart, no deploy |
| Extension version | N/A |
| Git | 1 commit (this report only) |
| Scope | 1 file (docs) |

---

## Not done / next

**Phase 1 (needs Cursor ACK first):** implement drain-this-lane (I1/I2) exactly as designed above, plus the duplicate-safe approve fix (I6). Verify via pytest for the drain stop-condition and the UniqueViolation-skip path.
**Phase 2 (after Phase 1 ACK):** shrink both home panels to the button lists above, stand up the shared Extras destination, delete the four duplicate buttons identified in I3/I5, restore inbox batch to `review_batch_size()` default (I7) while keeping the manual instant-flush override.
**Phase 3 (optional, after Phase 2 ACK):** soft-deprecate `/intake` and per-lane flush chrome that's now redundant with Extras; update `STORAGE_HUB_PANEL_MANUAL.md` to match.

---

**Phase 0 done — STOP for Cursor `/cc-report`. Do not start Phase 1.**
