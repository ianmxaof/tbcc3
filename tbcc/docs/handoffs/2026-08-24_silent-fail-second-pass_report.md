# Reverse handoff — silent-fail second-pass (Phases 0–1)

**Date:** 2026-08-24  
**Against:** operator-pasted directive (silent-fail / zombie-pass contract)  
**Phase:** 0–1 ACK’d → **2 complete** (B then D)  
**Status:** Pilots implemented; STOP for operator ACK / island dry-run optional

## Done

Read-only inventory of existing TBCC non-activity / stall detectors. Mapped each to failure class:

| Class | Meaning |
|-------|---------|
| **1 process-down** | PID/worker/API missing or unreachable |
| **2 work-never-ran** | Process/stack up (or Beat registered) but success/activity never observed or older than expected cadence — true silent abandon |
| **3 intentional-idle** | Gated off, governor-idle, or env-disabled — not a zombie |

**Do not confuse:** `network_liveness_*` / AOF network liveness = content posting cadence, **not** process zombie detection.

## Inventory table (≥6)

| # | Primitive | Path | Detects (class) | Gap vs “months-later dormant” |
|---|-----------|------|-----------------|-------------------------------|
| 1 | Idle Service Governor | `tbcc/backend/app/services/idle_service_governor.py` | **1** (logs when `celery_ops` appears DOWN); **3** (desired-state idle via Redis `tbcc:idle:{name}:active`, `touch_service_activity` / `last_activity`) | Does **not** flag Beat tasks that registered but never succeeded. Fail-open when governor off. Opt-in `TBCC_IDLE_GOVERNOR_ENABLED`. |
| 2 | Scheduling health | `tbcc/backend/app/services/system_health.py` (`collect_scheduling_health`, `cached_scheduling_health`) | **1** — Beat / Celery / `celery_ops_worker_running` process counts | Process-up only. No per-task `last_success` / `never_seen`. |
| 3 | Tray meltdown / THROTTLE / STALE | `tbcc/tools/tbcc-supervisor-panel.ps1`; docs `tbcc/docs/REVENUE_ISLAND.md` (~L342) | **1** — API poll stale / host throttle / panel honesty | Home-tray observability. Not island Beat “task never fired”. Smoke, not greenfield. |
| 4 | Stack status API | `tbcc/backend/app/api/ops_stack.py` → `get_stack_status` | **1** when tray present | On island: `available:false` (requires Windows tray) — cannot be the always-on island truth alone. |
| 5 | Ops picture blockers | `tbcc/backend/app/services/ops_picture_report.py` (`derive_blockers`, `scheduling_fast_snapshot`) | Mixed **1**/revenue blockers (point-in-time) | Not a cadence registry; no `never_seen` for optional Beat keys. |
| 6 | Post scheduler drain / orphans | `tbcc/backend/app/services/post_scheduler.py` (`ensure_post_drain_consumer`, `tbcc:post:drain_tick`, `tbcc:post:due_queue`) | **2** for **post queue only** — stale tick with no consumer; orphaned due_queue rows | Narrow vertical. Pattern to reuse; not a general second-pass. |
| 7 | Intake last_run Redis | `tbcc/backend/app/services/intake_scheduler.py` (`get_last_run_ts`, `mark_last_run`, enablement snapshot) | **2**/cadence when intake enabled — `last_run_ts` per lane | Closest existing “last success” shape. No global protocol wrapping it; silent if operator never reads snapshot. |
| 8 | Storage Hub op status | `tbcc/backend/app/services/storage_hub_op_status.py` | Operator-visible progress (anti-silent **UI** during hub ops) | Ephemeral Telegram status lines — not a dormant Beat/task registry. |
| 9 | Island Beat gates (tests) | `tbcc/backend/tests/test_celery_island_beat_gates.py` (+ `celery_app` beat_schedule) | Registration presence/absence by island vs home (**3**/env gates) | Proves keys **registered**, not that they **ever fired successfully** in prod. |

### Taxonomy verdict (ACK this)

| Class | Covered today? | Second-pass role |
|-------|----------------|------------------|
| 1 process-down | **Mostly covered** (scheduling health, governor ops warning, tray STALE/THROTTLE) | Protocol should **reuse**, not fork a parallel health stack. |
| 2 work-never-ran | **Thin / local only** (post drain, intake last_run) | **Primary miss** — registry of `enabled ∧ expected_cadence ∧ (never_seen ∨ last_success > threshold)`. |
| 3 intentional-idle | **Covered by design** (governor skip, `*_ENABLED=0`, island Beat omit) | Fence: idle-desired ≠ zombie. |

## External stop evidence (Phase 0 dry-read only)

Not a pilot watch yet — proves island reachable + stack-status limitation:

```powershell
# External stop: HTTP body must contain "ok" / status — not agent claim
(Invoke-WebRequest -Uri "https://api.powercore.app/health" -UseBasicParsing -TimeoutSec 15).Content
# Observed 2026-08-24: {"status":"ok","external_payment_orders_impl":"uuid-epo-v2","crypto_auto_checkout":true}

(Invoke-WebRequest -Uri "https://api.powercore.app/ops/stack-status" -UseBasicParsing -TimeoutSec 15).Content
# Observed: {"ok":false,"available":false,"error":"stack status requires Windows tray supervisor (tbcc-stack-cli.ps1)"}
```

Class-1 island truth must prefer `/health` + scheduling signals inside the API/worker path, not home tray stack-status.

## Candidate watches for Phase 1 naming (≤5, design only — no mutate)

| Candidate | Prove last_success / never_seen via | Class focus |
|-----------|-------------------------------------|-------------|
| A. `celery_ops` worker | `cached_scheduling_health` → `celery_ops_worker_running` | 1 (reuse) |
| B. Intake lanes | Redis `tbcc:intake:*:last_run` via `intake_scheduler` snapshot helpers | 2 |
| C. Post drain | Redis `tbcc:post:due_queue` length + `drain_tick` | 2 (existing healer) |
| D. Island Beat key e.g. `storage-hub-r2-export` | Celery result/event or DB side-effect timestamp (TBD in P1) | 2 gap |
| E. Governed service last_activity | Redis `tbcc:idle:{name}:last_activity` — careful: absence may mean **3** | 2 vs 3 fence |

## Files touched

- `tbcc/docs/handoffs/2026-08-24_silent-fail-second-pass_report.md` (this file)

**Not touched:** `CURRENT_DIRECTIVE.md` (loot-forum-twin remains), skills, runtime code, bots, `.env`.

## Verification (Phase 0)

1. Inventory rows: **9** (≥6) with paths — pass  
2. Skill file: **not yet** (Phase 1) — deferred  
3. Dry-read health command documented with observed body — pass  
4. No tray Start; no `.env` commit — pass  

## Risks

- Confusing network liveness posters with zombie-pass (called out).  
- False positives if Phase 1 treats governor-idle or `*_ENABLED=0` as never_seen.  
- Overwriting CURRENT_DIRECTIVE would collide with loot-forum-twin — avoided.

## Do not continue until ACK

**ACK asks (reply with picks):**

1. **Taxonomy OK?** Classes 1/2/3 as above.  
2. **Skill name:** `/silent-fail` (recommended) vs `/zombie-pass`.  
3. **Unlock Phase 1?** Author `~/.cursor/skills/tbcc-silent-fail/SKILL.md` (+ optional `.claude` twin / docs paste) with external-stop schema, always-on vs conditional table, Compose → after `/crew` / multiphase handoff.  
4. **Pilot preference for Phase 2 (later):** B intake last_run vs D one island Beat side-effect — or “document-only wrap of scheduling_health”.

## Phase 1 — Protocol/skill contract (2026-08-24)

**Operator ACK:** taxonomy 1/2/3 OK; name `/silent-fail`; unlock Phase 1; pilot (#4) deferred to discuss after P1.

### Done

- Cursor skill: `~/.cursor/skills/tbcc-silent-fail/SKILL.md` (GSP v2.4 — Purpose/When/Skip/Output/External stops/Fence/Compose)
- CC twin: `.claude/skills/tbcc-silent-fail/SKILL.md`
- Registry sketch (design only): `tbcc/docs/SILENT_FAIL_REGISTRY.example.json`
- `.claude/CLAUDE.md` skills table row added
- `protocol-chains.json` still missing in repo — Compose edges live in the skill Exit Conditions for now (conductor will no-op until chains file exists)

### Verification (Phase 1)

1. Inventory ≥6 — still in Phase 0 section — pass  
2. Skill contains Purpose, When, Skip, Output Contract, External stops schema, Fence — pass  
3. Worked example: health HTTP + intake `last_run` shape documented in skill — pass  
4. No tray Start; no runtime mutate; no CURRENT_DIRECTIVE overwrite — pass  

### Files touched (Phase 1)

| Path | Action |
|------|--------|
| `C:\Users\ianmp\.cursor\skills\tbcc-silent-fail\SKILL.md` | created |
| `.claude/skills/tbcc-silent-fail/SKILL.md` | created |
| `tbcc/docs/SILENT_FAIL_REGISTRY.example.json` | created (design) |
| `.claude/CLAUDE.md` | skills table +1 |
| `tbcc/docs/handoffs/2026-08-24_silent-fail-second-pass_report.md` | this update |

### Do not continue Phase 2 until pilot pick

~~Discuss~~ — operator picked **B then D** (2026-08-25).

## Phase 2 — Pilots B then D (2026-08-25)

### Done

| Pilot | Watch | Evidence | Command |
|-------|-------|----------|---------|
| **B** | intake lane `last_run` | Redis via `intake_scheduler` | `py -3.13 scripts/silent_fail_probe.py intake --lane inbox` |
| **D** | Beat `storage-hub-r2-export` | `Media.classification_json.r2.exported_at` | `py -3.13 scripts/silent_fail_probe.py r2-export` |

- Service: `tbcc/backend/app/services/silent_fail_probes.py`
- CLI: `tbcc/backend/scripts/silent_fail_probe.py` (also `all`)
- Tests: `tbcc/backend/tests/test_silent_fail_probes.py` — **8 passed**
- Skills/registry/TEST_MAP updated

### Verification

```powershell
cd tbcc/backend
py -3.13 -m pytest tests/test_silent_fail_probes.py -x -q --tb=short
# 8 passed

py -3.13 scripts/silent_fail_probe.py intake --lane inbox
# local dry-run 2026-08-25: idle (intake not enabled on this host) — exit 0

py -3.13 scripts/silent_fail_probe.py r2-export
# local dry-run: idle (R2 export not enabled / not island) — exit 0
```

Island (when operator wants live class-2 truth): run the same commands with island `REDIS_URL` / `DATABASE_URL` (or on the VPS). Expect `ok|stale|never_seen` when enablement is on.

### Files touched (Phase 2)

| Path | Action |
|------|--------|
| `tbcc/backend/app/services/silent_fail_probes.py` | created |
| `tbcc/backend/scripts/silent_fail_probe.py` | created |
| `tbcc/backend/tests/test_silent_fail_probes.py` | created |
| `tbcc/docs/TEST_MAP.md` | row |
| `tbcc/docs/SILENT_FAIL_REGISTRY.example.json` | pilots marked implemented |
| `~/.cursor/skills/tbcc-silent-fail/SKILL.md` | v1.1 |
| `.claude/skills/tbcc-silent-fail/SKILL.md` | worked example |
| this report | Phase 2 section |

### Risks

- Local/home env often prints `idle` (class 3) — not a false zombie; island enablement required for real never_seen/stale.
- R2 probe samples recent rows with `"exported_at"` — if stamps exist only on very old low-id rows outside the sample window, could false `never_seen` (mitigate: raise `--sample`).
- No auto-restart (by design).

### STOP

Phase 2 complete. Optional next: island dry-run of `silent_fail_probe.py all --json`; wire `protocol-chains.json` Compose edge; or expand registry watches.
