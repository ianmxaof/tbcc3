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
