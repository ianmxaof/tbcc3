# TBCC ops triage (Tiers 1–5)

Operator path when Secretary inbox shows critical ops alerts (session lock storm, tracebacks, port conflicts).

## Tier 0 — Auto-react (already configured)

| Env | Purpose |
|-----|---------|
| `TBCC_FOCUS_AUTO_REACT=1` | Auto-apply `telegram_relief` on lock storms |
| `TBCC_FOCUS_LOCK_EVENTS_THRESHOLD=3` | Events in window before storm |
| `TBCC_FOCUS_LOCK_WINDOW_S=120` | Rolling window |

Backend watch loop (`main.py`) calls `evaluate_and_maybe_auto_apply()` every ~25s.

**Verify (backend running):**

```powershell
curl http://127.0.0.1:8000/ops/focus
curl -X POST http://127.0.0.1:8000/ops/focus/evaluate/auto
```

Or in Secretary DM: `/focus` · `/relief`

**Last check (local):** `TBCC_FOCUS_AUTO_REACT=1`, lock events calm, profile restored to `off` after idle. Restart backend + Secretary to load new triage buttons.

## Tier 1 — Secretary buttons (free)

Critical/important **ops** instant DMs include:

- **Telegram relief** — `telegram_relief` focus profile
- **Copy for Cursor** — triage bundle (error-hub tail + focus state)
- **Agent triage** — gated Cursor run (Tier 5)

Commands: `/relief` · `/focus` · `/triage [event_id]` · `/status`

Env: `TBCC_INBOX_OPS_ACTIONS=1` (default on)

## Tier 2 — Selective hub scan

| Env | Default | Meaning |
|-----|---------|---------|
| `TBCC_ALERTS_HUB_SCAN=1` | off in old example | Scan `.tbcc-run/error-hub.log` |
| `TBCC_ALERTS_HUB_CRITICAL_ONLY=1` | on | Skip warning-level hub toasts |

Tracebacks classify as **critical** when critical-only mode is on.

## Tier 3 — Cursor Automation

See [CURSOR_OPS_AUTOMATION.md](./CURSOR_OPS_AUTOMATION.md) for a ready-to-paste automation draft (poll local ops API, diagnose-only, critical allowlist).

## Tier 4 — Cursor SDK bridge

| Env | Purpose |
|-----|---------|
| `TBCC_CURSOR_TRIAGE_ENABLED=1` | Enable Agent triage button + API |
| `CURSOR_API_KEY` | Cursor API key |
| `TBCC_CURSOR_TRIAGE_MAX_PER_DAY=3` | Daily cap |
| `TBCC_CURSOR_TRIAGE_AUTO_FIX=0` | Diagnose-only (set `1` for gated auto-patch) |
| `TBCC_CURSOR_TRIAGE_PR_ONLY=1` | Auto-fix must branch + PR; never push main |
| `TBCC_CURSOR_TRIAGE_AUTO_FIX_ALLOWLIST` | Subset of codes that may patch (`session_sqlite_lock`, `uvicorn_orphans`) |

```powershell
pip install cursor-sdk
curl http://127.0.0.1:8000/ops/triage/status
curl http://127.0.0.1:8000/ops/triage/bundle/<event_id>
curl -X POST http://127.0.0.1:8000/ops/triage/run -H "Content-Type: application/json" -d "{\"event_id\":\"<id>\"}"
```

## Tier 5 — Ops flywheel (OpenClaw + approve-before-fix)

| Env | Purpose |
|-----|---------|
| `TBCC_FLYWHEEL_ENABLED=1` | Skill registry router |
| `TBCC_FLYWHEEL_APPROVAL=1` | Approve/Reject in Secretary before destructive fixes |
| `TBCC_CURSOR_TRIAGE_ENABLED=1` | Agent triage button (needs `CURSOR_API_KEY`) |

**OpenClaw stub (one-shot tick):**

```powershell
cd tbcc\scripts
.\run-openclaw-ops-tick.ps1
.\run-openclaw-ops-tick.ps1 -DryRun   # if you add the switch later
```

**Skill registry** (`app/services/ops_flywheel.py`):

| Code | Lane |
|------|------|
| `session_lock_storm` | deterministic → telegram_relief |
| `worker_crash` | Claude Code handoff → **Approve** in Secretary |
| `service_traceback` | Cursor agent (if enabled) → Approve |
| `api_port_duplicate` | Claude Code handoff → Approve |

Secretary: `/flywheel` · **Approve fix** / **Reject** on flywheel DMs.

## Operator permissions (OpenClaw vs Secretary)

YAML matrix: `app/data/ops_tool_permissions.yaml`

| Operator | MCP flywheel_approve | Flywheel tick |
|----------|---------------------|---------------|
| `openclaw` / `cron` | **Denied** — notify only | Allowed |
| `secretary` | Allowed | Allowed |
| `api` | Allowed (localhost scripts) | Allowed |

```powershell
curl "http://127.0.0.1:8000/ops/flywheel/permissions?operator=openclaw"
curl -X POST "http://127.0.0.1:8000/ops/flywheel/approve/ABC123?operator=openclaw"   # → 403
```

OpenClaw must use **@aof_secretary_bot** Approve/Reject buttons, not MCP `flywheel_approve`.

## Ops workflow (YAML runner)

Pattern from `openclaw-orchestration` — lives in TBCC (no port conflict):

```powershell
curl -X POST http://127.0.0.1:8000/ops/workflow/run -H "Content-Type: application/json" -d "{\"operator\":\"openclaw\"}"
py -3.13 tbcc/backend/scripts/run_ops_workflow.py --operator openclaw
```

Steps: health → scheduling → flywheel tick → approval gate → handoff markdown.

Definition: `app/data/ops_workflow.yaml` · Runner: `app/services/ops_workflow_runner.py`

## Handoff reports

Structured ops output for OpenClaw / Cursor: [OPS_HANDOFF_PROTOCOL.md](./OPS_HANDOFF_PROTOCOL.md)

OpenClaw skill for failure modes: `docs/openclaw-skill/tbcc-failure-modes/SKILL.md`

## Files

- `app/services/admin_inbox.py` — instant DM + inline keyboard
- `app/services/ops_flywheel.py` — router + registry + pending approvals
- `app/services/ops_tool_permissions.py` — operator role gates
- `app/services/ops_workflow_runner.py` — YAML workflow executor
- `app/data/ops_tool_permissions.yaml` — permission matrix
- `app/data/ops_workflow.yaml` — tbcc_ops_turn workflow
- `app/api/ops_flywheel.py` — HTTP API
- `app/api/ops_workflow.py` — workflow + permissions API
- `backend/scripts/run_tbcc_flywheel_tick.py` — internal flywheel tick
- `backend/scripts/run_ops_workflow.py` — CLI workflow runner
- `scripts/run-tbcc-flywheel-tick.ps1` — Windows launcher
