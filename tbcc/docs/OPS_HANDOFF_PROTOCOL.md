# TBCC ops handoff protocol

Standard structure for ops reports produced by OpenClaw, Cursor triage, or flywheel — consumed by you or an implementation agent.

Adapted from `agent-skills/protocols/handoff-protocol.md` for TBCC / AOF Network.

## When to use

- OpenClaw finishes a diagnostic turn (scheduler stall, health check, failure-mode sim)
- Cursor triage (`/triage`, Agent triage button) completes diagnose-only run
- Flywheel routes an event to Claude Code handoff lane
- Manual ops investigation before approving a flywheel action

## Required sections

### 1. Context Summary

- What was checked (health, scheduling, flywheel, specific service)
- Scope (time window, services running, stack profile: lean / full / API-only)
- Assumptions (e.g. Redis expected up, Beat tab open)

### 2. Findings

Each finding includes:

| Field | Values |
|-------|--------|
| Priority | **P0** (outage) · **P1** (degraded now) · **P2** (relief needed) · **P3** (informational) |
| Code | Flywheel/inbox code if known (`redis_down`, `worker_crash`, `session_sqlite_lock`, …) |
| Description | Plain language |
| Evidence | Log line, API snippet, MCP tool result |

Map to flywheel priority: P0 = redis/backend dead; P1 = worker_crash, 409, port duplicate; P2 = traceback, session lock.

### 3. Recommendations

- Actionable fix (restart which tab, run which script)
- Estimated effort (minutes)
- Whether **Secretary Approve** or **OpenClaw notify-only** applies
- Dependencies (Redis before Celery, gateway before cron)

### 4. Implementation Steps

Ordered, specific steps:

```text
1. Start Redis: cd tbcc/infra && docker compose up -d redis
2. Lean full stack: TBCC_STACK_PROFILE=lean; .\start.ps1 -Full -WtTabs -NoReload
3. Verify: mcporter call tbcc.tbcc_health
4. Reject stale flywheel pending if any: py -3.13 tbcc/backend/scripts/flush_flywheel_pending.py --older-than-days 1
```

### 5. Files to Modify / Create

Only when code change is recommended — path, change type, brief description. Default for ops: **no code changes**; stack/process fixes only.

### 6. Dependencies

- TBCC API :8000, Redis :6379, OpenClaw gateway :18789
- MCP: mcporter + `tbcc` server
- Skills used: `tbcc-aof-network`, `tbcc-failure-modes`

## Filename convention

```
YYYY-MM-DD_<source>_<target>.md
```

Examples:

- `2026-06-25_openclaw_scheduler-stall.md`
- `2026-06-25_cursor-triage_service-traceback.md`
- `2026-06-25_flywheel_worker-crash.md`

Store under `tbcc/docs/handoffs/` (create as needed) or paste into Secretary / OpenClaw chat.

## Context budget (>4000 tokens)

1. Main report: **P0–P1 only**, max 500-token executive summary at top
2. Companion file: `*-details.md` for P2–P3 and log excerpts
3. Link from main report to details

## Operator permissions

See `tbcc/backend/app/data/ops_tool_permissions.yaml`:

| Operator | Read health | Flywheel tick | Approve destructive |
|----------|-------------|---------------|---------------------|
| `openclaw` | yes | yes | **no** (notify + Secretary) |
| `secretary` | yes | yes | **yes** |
| `cursor_automation` | yes | diagnose | gated by allowlist |
| `cron` | yes | yes | **no** |

## Related

- [OPS_TRIAGE.md](./OPS_TRIAGE.md)
- [OPENCLAW_TBCC_INTEGRATION.md](./OPENCLAW_TBCC_INTEGRATION.md)
- [CURSOR_OPS_AUTOMATION.md](./CURSOR_OPS_AUTOMATION.md)
- OpenClaw skill: `tbcc/docs/openclaw-skill/tbcc-failure-modes/SKILL.md`
