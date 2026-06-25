# TBCC failure modes (OpenClaw skill)

Simulate and diagnose TBCC / AOF ops failure modes. Output follows `tbcc/docs/OPS_HANDOFF_PROTOCOL.md`.

## When to invoke

- User reports: stalled scheduler, hot CPU, notification storm, MCP errors, 409 conflicts
- Before approving flywheel restarts after a long outage
- Phrases: "run failure mode check", "stress test TBCC stack", "why is scheduling stalled"

## TBCC failure modes (6)

### 1. Stack overload (Critical)

**Triggers:** `start.ps1 -Full` + forum + enrichment + uvicorn `--reload`; many PowerShell/WT tabs.

**Checks:** Task Manager CPU; count TBCC processes; `GET /ops/stack` if available.

**Countermeasures:**
- Stop stack; use `TBCC_STACK_PROFILE=lean` + `-NoReload`
- `.\start.ps1 -Full -WtTabs -NoReload` only when posting needed
- OpenClaw gateway separate from TBCC — don't run duplicate backends

### 2. Scheduler stall (Critical)

**Triggers:** Redis down; Celery Beat not running; Celery-Post worker missing; focus profile pauses beat.

**Checks:**
- `mcporter call tbcc.tbcc_health`
- `mcporter call tbcc.list_scheduled_posts` (MCP must be up)
- `GET http://127.0.0.1:8000/health` scheduling section if present
- Confirm `TBCC-Beat` and `TBCC-Celery-Post` tabs exist

**Countermeasures:** Start Redis → lean full stack → verify beat every 2m (`TBCC_BEAT_SCHEDULE_MINUTES`)

**Not OpenClaw cron:** `openclaw cron list` is separate; 0 jobs does not stall Telegram posts.

### 3. MCP bridge failure (High)

**Triggers:** TBCC API restarting; mcporter spawn timeout; Python 3.13 MCP server crash.

**Symptoms:** `MCP error -32000: Connection closed`, mcporter timeouts.

**Countermeasures:**
- Ensure API stable first
- `mcporter call tbcc.tbcc_health --config ~/.openclaw/config/mcporter.json`
- Copy mcporter.json to workspace `./config/mcporter.json`
- Retry once; if persistent, report P1 and stop (don't loop)

### 4. Notification storm (High)

**Triggers:** `TBCC_INBOX_OPS_ACTIONS=1` + sick stack; stale flywheel pending; hub scan instant.

**Checks:** `flywheel_approval_bundle` pending_count; Secretary DM rate.

**Countermeasures:**
- Stop stack to halt new alerts
- After API+Redis up: `py -3.13 tbcc/backend/scripts/flush_flywheel_pending.py --older-than-days 0 --all`
- Temporarily set `TBCC_INBOX_HUB_BATCH_INSTANT=0` during recovery

### 5. Telegram 409 conflict (Critical)

**Triggers:** Same bot token on two processes (Secretary vs OpenClaw vs duplicate loot bot).

**Checks:** Flywheel code `telegram_409_conflict`; multiple bot PIDs.

**Countermeasures:** One token per bot; OpenClaw uses `@openclawtbcc_bot` only; kill duplicate bot processes.

### 6. Session SQLite lock storm (P2)

**Triggers:** Shared Telethon session; too many concurrent scrapes/posts.

**Checks:** Inbox `session_lock_storm` / `session_sqlite_lock`; `/ops/focus`.

**Countermeasures:** `telegram_relief` focus profile; dedicated sessions per worker; reject stale flywheel items.

## Execution modes

### Full scan

Run all 6 modes in order. Produce handoff with P0–P1 findings first.

### Targeted

User names one mode (e.g. "scheduler stall") — deep dive that mode only.

## Output contract

Use **OPS_HANDOFF_PROTOCOL** sections:

1. Context Summary (stack profile, what's running)
2. Findings (P0–P3 + evidence from mcporter/API)
3. Recommendations (no auto-approve flywheel unless user explicitly said so)
4. Implementation Steps (scripts/commands)
5. Files to Modify — only if code fix needed
6. Dependencies

Filename suggestion: `YYYY-MM-DD_openclaw_failure-mode-scan.md`

## Permissions

OpenClaw operator role: read + tick + notify. **Do not** `flywheel_approve` unless user says "approve action X". See `ops_tool_permissions.yaml`.

## Related tools

- `tbcc_health`, `list_scheduled_posts`, `tbcc_flywheel_tick`, `flywheel_approval_bundle`
- Docs: `tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md`, `tbcc/docs/OPS_HANDOFF_PROTOCOL.md`
