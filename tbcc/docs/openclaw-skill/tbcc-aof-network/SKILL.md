# TBCC + AOF Network operator (OpenClaw skill)

Use when managing the Telegram Bot Command Center (TBCC) and AOF content network on the operator machine.

## Prerequisites

- TBCC API on `http://127.0.0.1:8000` (`tbcc/start.ps1` or supervisor tray)
- Celery + Redis for posts/imports (`start.ps1 -Full` or lean + workers)
- TBCC MCP tools connected (`tbcc_health`, `tbcc_flywheel_tick`, `flywheel_approval_bundle`)

## Every ops turn

1. Call `tbcc_health`.
2. Call `tbcc_flywheel_tick` with `ops_limit=1` OR read status only if user asked diagnose-only.
3. Call `flywheel_approval_bundle`. If pending items exist, **summarize for the user** — do not auto-approve unless user explicitly said auto-approve mode.

## Approval policy (critical)

| Action | Default |
|--------|---------|
| Flywheel **Approve** (restart, Cursor triage) | Ask user in OpenClaw chat OR tell them to tap **Approve** in **@aof_secretary_bot** |
| Live Telegram post / deposit / campaign change | Always ask first |
| Code edits | Branch + PR only; never push main |
| Browser login / payment | Never without user |

Secretary bot = human approval UI. OpenClaw bot = your operator channel (separate BotFather token).

## Priority (what to fix first)

1. **P0** — `redis_down`, backend :8000 dead, Celery stopped
2. **P1** — `worker_crash`, `telegram_409_conflict`, `api_port_duplicate` (if happening **now**)
3. **P2** — `service_traceback`, `session_sqlite_lock` (relief + dedicated Telethon sessions)
4. **Reject** — pending items older than 24h unless errors recur today

## TBCC MCP tools (common)

- `list_channels`, `list_pools`, `list_scheduled_posts`
- `create_scheduled_post`, `trigger_scheduled_post`, `schedule_recurring_campaign`
- `import_media_url`, `analytics_weekly_summary`
- `tbcc_flywheel_tick`, `flywheel_approval_bundle`, `flywheel_approve`, `flywheel_reject`

## AOF network map (repo)

- Channels/pools: `tbcc/backend/app/data/aof_network.py`
- Storage hub `/deposit`: Storage Hub subtopics, secretary `/deposit`
- Ops playbooks: `tbcc/backend/app/services/cursor_triage_playbooks.py`

## Cron suggestion (OpenClaw)

Every 20 min — ops pulse (`tbcc-ops-check`):

> Run tbcc_health. If OK, tbcc_flywheel_tick(ops_limit=1). If flywheel_approval_bundle has pending, message user with top item only — do not spam.

Every 30 min — growth report (`tbcc-growth-report`, skill `tbcc-growth-signals`):

> analytics_content_performance(run_tick=true). Deliver full markdown + 2-sentence executive summary. Never auto-post.

Install: `tbcc\scripts\setup-openclaw-growth-cron.ps1`

## Do not confuse

- **TBCC flywheel tick** = internal TBCC API poller (`/analytics/tbcc-flywheel/tick`)
- **You (OpenClaw)** = autonomous operator with shell/browser + TBCC MCP

Docs: `tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md`

## Failure modes + workflow

- Full scan: load skill `tbcc-failure-modes` when user reports stall, hot CPU, or notification storm
- Structured output: `tbcc/docs/OPS_HANDOFF_PROTOCOL.md`
- One-shot workflow: MCP `run_ops_workflow` or `POST /ops/workflow/run`
