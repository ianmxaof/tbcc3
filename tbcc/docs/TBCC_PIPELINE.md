# TBCC import pipeline and system health

## Fast import (instant extension ack)

When `TBCC_FAST_IMPORT=1` (default):

1. Extension POSTs bytes to `/import/bytes`.
2. API stages file under `tbcc/.tbcc-run/import-staging/` and returns `{ job_id, status: "queued", poll_url }` immediately.
3. Celery task on the **`telegram`** queue uploads to Saved Messages / pool (serialized Telegram I/O).
4. Extension polls `GET /import/jobs/{job_id}` until `status` is `done` or `failed`.

Gallery jobs show live stage labels (stored → queued → telegram → done).

### Celery queues

Worker must consume: `celery,post,scrape,subscription,telegram` (see `start.ps1`).

### Ops endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health/system` | Redis, ports, session conflicts, active import jobs |
| `GET /import/jobs/{id}` | Poll one import job |
| `GET /import/jobs?active=1` | List in-flight jobs |
| `POST /import/jobs/{id}/cancel` | Cancel staged/queued import (revokes Celery task) |
| `GET /import/queue/status` | Celery telegram queue depth + active DB jobs |

**Extension:** service worker uses `chrome.alarms` to keep polling `backendJobId` after reload; gallery reconciles with `?active=true` on open. **Pause queue** stops new `/import/bytes` posts; **Cancel** per job in Running tasks.

### Stability scripts

- `scripts/tbcc-cleanup-orphans.ps1` — kill uvicorn `multiprocessing-fork` workers blocking :8000
- `scripts/tbcc-stack-preflight.ps1` — Redis/Postgres/orphan checks before cold start
- `scripts/show-tbcc-processes.ps1` — map `python.exe` rows to TBCC-* services (RAM, ports, API `/health/system`); `-Watch -IntervalSec 5` to refresh

### Process / network monitoring (Windows)

| What you need | Where |
|---------------|--------|
| Named services vs generic `python.exe` | `.\scripts\show-tbcc-processes.ps1` or Windows Terminal tabs titled `TBCC-*` (`start.ps1 -Full -WtTabs`) |
| Per-service up/down | Tray `tbcc\tools\tbcc-supervisor.ps1` |
| Errors across tabs | `TBCC-Errors` tab / `.tbcc-run\error-hub.log` |
| Breaking conflict / hub alert toasts | `GET /ops/alerts/poll` — extension, dashboard, tray supervisor |
| Session lock, import queue, Redis | Dashboard system health banner → `GET /health/system` |
| Which PID is using bandwidth | `resmon.exe` → **Network** → sort **Total (B/sec)**; or Task Manager **Details** → enable **Command line** |
| Docker | Only **Postgres + Redis** for TBCC; `docker ps`. Host Python (API, Celery, bots, NSFW, CLIP) is outside Docker. |

Watch-folder organizer is a **separate** process (`python -m app.services.watch_folder_organizer`); it appears as `TBCC-WatchOrganizer` in the process monitor when running.

### Full stack defaults

`start.ps1 -Full -WtTabs` uses **`-NoReload`** unless you pass `-Reload` (avoids orphan API listeners on Windows).

See also `docs/TELEGRAM_OPS.md` for SQLite session lock storms.

## PowerShell versions (tray / cold start vs Cursor)

| Shell | Used for |
|-------|----------|
| **Windows PowerShell 5.1** (`powershell.exe` in `System32\...`) | TBCC tray cold start, `start.ps1`, restart scripts |
| **PowerShell 7** (`pwsh`, e.g. [7.6.2 LTS](https://github.com/PowerShell/PowerShell/releases/tag/v7.6.2)) | Optional; Cursor/VS Code integrated terminal often uses this |

Updating **pwsh** does not change TBCC launchers (they call `powershell.exe` explicitly).

If **“PowerShell Extension Terminal has stopped”** appears in Cursor, that is the **editor extension** (pwsh language host), not the TBCC cold-start window. Upgrade **pwsh** to [7.6.2](https://github.com/PowerShell/PowerShell/releases/tag/v7.6.2) (fixes local user config path checks), then click **Yes** to restart the extension or **Developer: Reload Window**. It is unrelated to Docker unless Docker Desktop restarted WSL.

```powershell
# Approve UAC when prompted
powershell -ExecutionPolicy Bypass -File tbcc\tools\upgrade-powershell-7.6.2.ps1
```

**Bug fixed:** never use `$pid` as a `foreach` loop variable in TBCC scripts — it overwrites the automatic `$PID` and could cause the cold-start window to be killed during stack stop.
