# Cursor Automation — TBCC ops triage (setup checklist)

Phases 1–5 of the ops automation ladder are configured in `.env` (see `OPS_TRIAGE.md`). This doc covers **Tier 3** — the scheduled/manual Cursor Automation agent.

## Quick setup (Windows)

```powershell
cd tbcc\scripts
.\setup-cursor-ops-automation.ps1
.\register-cursor-ops-automation-task.ps1 -IntervalMinutes 15   # local automation tick
.\register-openclaw-scheduled-task.ps1 -IntervalMinutes 15      # flywheel + growth
```

**Local automation (step 3 substitute):** Windows Task `TBCC-Cursor-Ops-Triage` runs the same poll/flywheel/focus logic as the Cursor cloud automation. You can still add the cloud automation in Cursor → Automations using the prefill JSON below for IDE-side agent runs.

Then paste `tbcc/docs/automations/tbcc-ops-triage-prefill.json` into Cursor Automations (or use the Instructions block below).

## What you do in Cursor (Tier 3)

1. Open **Cursor → Automations** (Agents Window recommended).
2. **New automation** → name: `TBCC critical ops triage`.
3. **Trigger:** Manual first — add **cron every 15 min** (`0 */15 * * * *`) once stable.
4. **Repo:** this workspace (`telegram_bot2` / `c:\Powercore-repo-main\telegram_bot2`).
5. **Tools:** Terminal (+ read files under `tbcc/`).
6. Paste the **Instructions** block below (includes session-lock playbooks).
7. Save. Run once manually while TBCC-Backend is on `:8000`.

Prefill JSON (for Automations editor import): `tbcc/docs/automations/tbcc-ops-triage-prefill.json`

## Instructions (paste into automation prompt)

```
You are TBCC on-call triage. Run ONLY when the poll step finds a NEW critical alert.

## Poll + route
1. curl -s http://127.0.0.1:8000/ops/alerts/poll
2. If alerts[] is empty, exit with "no new alerts".
3. For each alert where severity is critical AND code is one of:
   session_lock_storm, session_sqlite_lock, worker_crash, api_port_duplicate,
   uvicorn_orphans, service_traceback, redis_down — process at most ONE alert per run.
4. curl -s http://127.0.0.1:8000/ops/flywheel/tick -X POST -H "Content-Type: application/json" -d "{\"limit\":1}"
   (routes through skill registry; Secretary Approve for worker_crash / uvicorn_orphans / service_traceback)
5. curl -s http://127.0.0.1:8000/ops/focus
6. curl -s http://127.0.0.1:8000/ops/triage/status

## session_sqlite_lock playbook
Symptom: sqlite3.OperationalError database is locked on Telethon .session files.
1. POST telegram_relief via /ops/focus or Secretary /relief.
2. Verify dedicated sessions — admin_bot must use admin_bot.session (not admin.session):
   tbcc/backend/app/utils/telethon_session.py → admin_bot_session_stem()
3. Bootstrap: TBCC_ADMIN_BOT_AUTO_COPY_ADMIN_SESSION=1 copies admin.session → admin_bot.session once.
4. WAL + busy_timeout: TBCC_TELEGRAM_SQLITE_BUSY_TIMEOUT_MS (default 120000).
5. Kill duplicate bot processes (one token = one process).
6. Do NOT full-stack restart unless backend is dead on :8000.

## session_lock_storm playbook
Multiple lock events in 120s window. Auto-react may already apply telegram_relief (TBCC_FOCUS_AUTO_REACT=1).
Split shared admin.session users onto dedicated stems; restore to off after idle.

## uvicorn_orphans playbook
Restart TBCC-Backend via supervisor only. Verify single listener on :8000 before restart.

## Agent triage (optional — needs CURSOR_API_KEY + TBCC_CURSOR_TRIAGE_ENABLED=1)
For allowlisted codes only:
  curl -s -X POST http://127.0.0.1:8000/ops/triage/run -H "Content-Type: application/json" -d "{\"event_id\":\"<id>\",\"source\":\"automation\"}"
Prefer Secretary Approve on flywheel DMs before auto-fix runs.
When TBCC_CURSOR_TRIAGE_AUTO_FIX=1 and code is in AUTO_FIX_ALLOWLIST:
  branch + PR only (TBCC_CURSOR_TRIAGE_PR_ONLY=1) — never push main.

## Output
Short markdown report: alert code, focus profile, flywheel result, recommended next step.
This automation must NOT edit files, commit, push, or restart services unless
TBCC_CURSOR_TRIAGE_AUTO_FIX=1 AND the operator has enabled PR-only auto-fix for that code.
```

## Prerequisites (machine must be on)

- TBCC-Backend running (`GET http://127.0.0.1:8000/ops/triage/status` returns JSON, not 404).
- Redis up (flywheel pending actions).
- Secretary bot running for approval DMs.
- `CURSOR_API_KEY` in `tbcc/.env` for SDK triage (`pip install cursor-sdk`).

## Verify tiers 1–5

```powershell
curl http://127.0.0.1:8000/ops/triage/status
curl http://127.0.0.1:8000/ops/flywheel/status
curl http://127.0.0.1:8000/ops/focus
```

Secretary DM: `/status` · `/flywheel` · `/triage <event_id>` · **Approve fix** on flywheel proposals.

## OpenClaw growth tick (content signals)

Same scheduler as ops tick, or run manually:

```powershell
cd tbcc\backend
py -3.13 scripts\run_openclaw_ops_tick.py          # ops + growth
py -3.13 scripts\run_openclaw_ops_tick.py --dry-run
py -3.13 scripts\run_openclaw_ops_tick.py --growth-only
```

API: `POST http://127.0.0.1:8000/analytics/openclaw/tick`

## Related

- [OPS_TRIAGE.md](./OPS_TRIAGE.md)
- OpenClaw stub: `tbcc/scripts/run-openclaw-ops-tick.ps1`
- Playbooks source: `tbcc/backend/app/services/cursor_triage_playbooks.py`
