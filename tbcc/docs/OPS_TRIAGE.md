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

## Files

- `app/services/admin_inbox.py` — instant DM + inline keyboard
- `app/services/ops_flywheel.py` — router + registry + pending approvals
- `app/api/ops_flywheel.py` — HTTP API
- `backend/scripts/run_openclaw_ops_tick.py` — OpenClaw stub
- `scripts/run-openclaw-ops-tick.ps1` — Windows launcher
- `app/services/ops_triage_bundle.py` — bundle builder
- `app/services/cursor_triage.py` — gated agent runs
- `app/api/ops_triage.py` — HTTP API
- `bots/secretary_bot.py` — `/relief` `/focus` `/triage` + callbacks
