# TBCC GSP Protocols

Protocols conform to **Global Protocol Standard v2.1** (`.cursor/rules/global-protocol-standard.mdc` in your local Cursor config). Personal skill copies live under `~/.cursor/skills/`; this file is the repo-backed index.

**Sprint warm-start:** agents read `tbcc/docs/SPRINT_STATE.md` before substantive work (see `.cursor/rules/sprint-state.mdc`).

**Always-apply rules:** `completion-gates.mdc`, `tbcc-dev-ops.mdc`, `bottom-line-next-steps.mdc`, `tbcc-agent-platform-routing.mdc`, `sprint-state.mdc`, `workflow-automation.mdc`, `global-protocol-standard.mdc`, `tbcc-daily-brief.mdc`.

**Lane calculus (v1.1):** execution → Auto (~80%); judgment gate (≥2 of revenue / multi-system / irreversible doctrine / leakage / critique / costly trade-offs) → Frontier Plan/Ask once, then Auto implement. Forbid Auto-stub on doctrine. Cloud remains rare (hard gate).

**Zero commands:** protocols fire on situation (see `workflow-automation.mdc`). Slash aliases optional.

## Automation stack

| Layer | Runs | Setup |
|-------|------|-------|
| Cursor hooks | Sprint state injected every session | `.cursor/hooks.json` |
| Always-apply rules | Preflight, gates, bottom line, daily brief triggers | automatic in Cursor |
| Windows task `TBCC-Ship-Log-Tick` | Weekly ship-log → Buffer | `tbcc/scripts/register-ship-log-scheduled-task.ps1` |
| Cursor Automation (optional cloud) | Same ship-log tick | `tbcc/docs/automations/tbcc-ship-log-weekly-prefill.json` |
| Ops triage (separate) | Critical alerts | `tbcc/docs/automations/tbcc-ops-triage-prefill.json` |

Ship-log env: `TBCC_SHIP_LOG_AUTO_MODE=idea|queue|share_now` in `tbcc/.env`

## Registered protocols

| Protocol | Triggers | Skill |
|----------|----------|-------|
| **TBCC Sprint Start** | `/sprint-start`, `start sprint`, `new sprint` | `~/.cursor/skills/tbcc-sprint-start/SKILL.md` |
| **TBCC Preflight** | `/preflight`, `TBCC preflight`, `plan before implementing` | `~/.cursor/skills/tbcc-preflight/SKILL.md` |
| **TBCC Session Close** | `/session-close`, `close session`, `wrap up` | `~/.cursor/skills/tbcc-session-close/SKILL.md` |
| **Claude Code Handoff** | `/handoff-cc`, `hand off to Claude Code`, `Lane C` | `~/.cursor/skills/handoff-claude-code/SKILL.md` |
| **Claude Code Reverse Report** | `/cc-report`, `Claude Code report`, `read the CC report` | `~/.cursor/skills/claude-code-report/SKILL.md` |
| **TBCC Ship Log** | `/ship-log`, `TBCC ship log`, `draft my build-in-public tweet` | `~/.cursor/skills/tbcc-ship-log/SKILL.md` |
| **TBCC Milestone Ship** | `/milestone-ship`, `TBCC milestone ship`, `ship milestone to GitHub` | `~/.cursor/skills/tbcc-milestone-ship/SKILL.md` |
| **TBCC Extension Errors** | `/ext-errors`, `check extension errors`, `TBCC extension errors` | `~/.cursor/skills/tbcc-ext-errors/SKILL.md` |
| **TBCC Daily Brief** | `/daily-brief`, `daily brief`, `bring me up to speed`, `loose ends` | `~/.cursor/skills/tbcc-daily-brief/SKILL.md` |
| **TBCC Sitrep** | `/sitrep`, `sitrep`, `situation report`, `mid-op status`, `what just shipped` | `~/.cursor/skills/tbcc-sitrep/SKILL.md` |
| **TBCC Ops Picture** | `/ops-picture`, `ops picture`, `health and analytics`, `financial ops report`, `what's broken in tbcc` | `~/.cursor/skills/tbcc-ops-picture/SKILL.md` |

### Protocol chains

- **Warm start:** `/daily-brief` → pick Top 5 → implement (or `/preflight` if ≥3 files)
- **Mid-op multitask:** `/sitrep` → pick Vector (or Wire/close fuse) → implement / tray ops
- **Money health check:** `/ops-picture` → pick blocker → fix / deploy / tray ops
- **New arc:** `/sprint-start` → `/preflight` (if ≥3 files) → implement → `/session-close`
- **Grind:** `/preflight` → `/handoff-cc` → Claude writes `tbcc/docs/handoffs/*_report.md` → `/cc-report` in Cursor → ACK → next phase or ship
- **Release:** `/milestone-ship` → optional `/ship-log`
- **Extension QA:** paste Errors screenshot or `/ext-errors` → fix / restart backend → re-check

## Tooling

| Script | Purpose |
|--------|---------|
| `backend/scripts/ops_picture_snapshot.py` | Consolidated analytics + error-hub JSON for `/ops-picture` |
| `backend/scripts/ship_log_sources.py` | Git + improvement-notes context |
| `backend/scripts/ship_log_buffer.py` | Buffer Idea or X queue |
| `backend/scripts/milestone_ship.py` | Status, push, full milestone pipeline |
| `backend/scripts/buffer_channels.py` | List Buffer org/channel ids |
| `backend/scripts/stock_buffer_armory.py` | Arm 12 X captions into relay/scheduler queues |

## Buffer armory (trigger-synced)

TBCC stores pre-written X captions in **`buffer_x_queue`** (not Buffer's native queue). One caption fires per Telegram send when `buffer_mirror_enabled` (scheduler) or `buffer_relay_enabled` (listening relay).

```powershell
py -3.13 scripts/stock_buffer_armory.py --preview
py -3.13 scripts/stock_buffer_armory.py --relay --scheduled
```

## Milestone ship flow

1. `py -3.13 scripts/milestone_ship.py --status`
2. Stage files (`git add tbcc/` …), exclude secrets per `tbcc/.gitignore`
3. `py -3.13 scripts/milestone_ship.py --execute -m "…" --post-variant 1`

Buffer: [developers.buffer.com](https://developers.buffer.com/guides/getting-started.html)

## Tray supervisor — single process control plane (v1.0)

**Purpose:** One owner for all TBCC OS processes on Windows. Prevents duplicate Telegram bots (409 Conflict), aligns dashboard status with the tray tooltip, and gives agents a single rule for start/stop.

**When to invoke:** Any time you need to start/stop/restart TBCC services, verify lean stack health, or wire dashboard bot controls.

### Lean vs full cold-start

- **`TBCC_STACK_PROFILE=lean` (default):** revenue-capable minimal — Docker Postgres/Redis + `backend` + `celery` + `beat` + `payment` + `loot`. Dashboard, secretary, album composer, post/ops Celery lanes, OpenClaw, forum/macro/admin/companion, and enrichment stay Off until enabled in tray Services.
- **`full`:** previous farm cold-start (dashboard + all Celery lanes + secretary + album + optional bots).
- **Revenue island cutover:** when money runs on a dedicated VPS, set `TBCC_REVENUE_ISLAND_ACTIVE=1` and keep home `payment`/`loot` Off (toggles + defaults) so a casual Start stack never Telegram-409s the island. See `docs/REVENUE_ISLAND.md`.

### Rules (mandatory for agents)

1. **Never** `POST /bots/runtime/*/start` while TBCC Supervisor tray tabs may be running — use tray or `command` adapter only.
2. **Never** spawn `python -m bots.payment_bot` (or loot/secretary) from a second terminal if a tray tab exists.
3. **Process control** → tray **Services** menu, or `tbcc\scripts\tbcc-stack-cli.ps1`.
4. **Telegram bots** talk to **TBCC API** for business logic only — they do not manage OS processes.
5. **Status truth ladder** → (1) `tbcc-stack-cli.ps1 -Action Status` / tray Services LEDs (process + port detection; works when API is down); (2) supervisor panel `THROTTLE`/`STALE` when host is hot or snapshot is old; (3) `GET /ops/stack-status` only when API is up (same `N/M running` model — useless during cold start if backend is still down).

### Architecture

```
TBCC Supervisor tray  ──owns──► lean: API, celery, beat, payment, loot (+ Docker PG/Redis)
        ▲
        │ tbcc-stack-cli.ps1 (Start/Stop/Restart/Status)
        │
Dashboard / API  ──command adapter──►  same tray scripts (no duplicate Popen)
        │
Telegram bots  ──HTTP──►  TBCC API  ──►  DB / Celery / poster
```

### CLI (JSON stdout)

```powershell
cd tbcc
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tbcc-stack-cli.ps1 -Action Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tbcc-stack-cli.ps1 -Action Restart -Service payment
```

Service ids: `backend`, `dashboard`, `celery`, `celery_post`, `beat`, `payment`, `loot`, `secretary`.

### Env

```env
TBCC_BOT_RUNTIME_ADAPTER=command   # default on Windows when unset
```

Commands auto-resolve from `tbcc-stack-cli.ps1` when `TBCC_*_BOT_CMD_*` are empty.

### Flywheel auto-fix (no Secretary approval)

- `worker_crash` → restart inferred service via tray
- `api_port_duplicate` → restart `backend`
- `telegram_409_conflict` → restart affected bot service

### Do not use

- `local` adapter on Windows when tray is in use (dev-only; causes 409).
- Starting bots via Cursor health-check without checking tray first.
