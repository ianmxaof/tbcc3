# TBCC Supervisor Panel — Phase 0 Assessment

_Lane C reliability + remote-deploy foundation. Files assessed: `tbcc/tools/tbcc-supervisor-panel.ps1`, `tbcc/tools/tbcc-supervisor.ps1`, `tbcc/scripts/tbcc-service-control.ps1`._

## A) Refresh pipeline — what blocks the UI thread

The panel is a WinForms app driven by `System.Windows.Forms.Timer`. That timer fires its `Add_Tick` handler **on the STA UI thread** — the same thread that pumps window messages (paint, drag, resize, mouse). Every byte of data acquisition therefore runs *inside the message pump*: while a tick runs, the window cannot paint, drag, or respond.

Full panel tick (`Show-TbccSupervisorPanel`, 4s interval, first tick at 250ms) calls `Get-TbccSupervisorHealthSnapshot` (non-Lite), which synchronously does, in order:

1. **`Get-TbccHostMetrics`** — CPU `PerformanceCounter.NextValue()` (cheap), RAM `Get-CimInstance Win32_OperatingSystem` (WMI, cached 2s), Net `Get-NetAdapterStatistics` (cmdlet, can be 100s of ms).
2. **`Update-TbccServiceStatusCache`** (only when the 8s svc cache is stale) — the heaviest block:
   - `Get-TbccListeningPortSet` → spawns **`netstat -ano`** subprocess (100s of ms, seconds under CPU pressure).
   - `Get-TbccWin32ProcessListCached` → `Get-CimInstance Win32_Process` **full command-line scan** (expensive; 15s TTL cache, but the miss is the single biggest stall — seconds under load).
   - Per service: `Get-TbccServiceStatusLabel` (regex over every process command line) + `Test-TbccServiceUserEnabled` (`.env` + toggles file reads).
3. **`Get-TbccListeningPortSet` AGAIN** for `$snap.Ports` (infra LEDs) → a **second `netstat -ano` spawn** every heavy tick.
4. **`Read-TbccErrorHubTail`** — file read (seeks last 256KB — already optimized from whole-file).
5. **`process-audit.json`** read + `ConvertFrom-Json`.
6. **`Invoke-RestMethod`** `/health/system` (2s timeout) then `/ops/alerts/poll` (2s timeout) → up to **4s of UI-thread block** if the API accepts the TCP connect but hangs. A 15s fail-backoff short-circuits repeated failures, but the first call after recovery still pays the timeout.

Mitigations already present (do not regress): a re-entrancy guard (`$script:TbccSupPanelBusy` / `…MiniBusy`) stops a slow tick from *stacking* a second; `WM_ENTERSIZEMOVE`/`WM_EXITSIZEMOVE` set `InteractionPaused` so ticks are skipped during drag/resize; mini and full forms are mutually parked so their timers never both run.

**Core gap:** the guard prevents *stacking* but never *yields*. A single heavy tick still freezes the pump for its full duration (netstat + WMI + up-to-4s HTTP). Under a CPU/RAM meltdown that duration balloons, and the freeze becomes visible as drag jank, a "busy" cursor, and unpainted window chrome.

## B) Data sources

| Signal | Source | Cost / cadence |
|---|---|---|
| CPU % | `PerformanceCounter` "% Processor Utility" (`Get-TbccCpuPercentFast`) | cheap, every tick |
| RAM % / used / total | WMI `Win32_OperatingSystem` (`Get-TbccRamMetricsCached`) | WMI, 2s cache |
| Net down/up | `Get-NetAdapterStatistics` delta (`Get-TbccNetworkSample`) | cmdlet, per tick |
| Listening ports (`:8000/:5173/:6379/:5432`) | `netstat -ano` parse (`Get-TbccListeningPortSet`) | subprocess, **twice** per heavy tick |
| Service up/down | WMI `Win32_Process` cmdline regex + port test (`Update-TbccServiceStatusCache`) | WMI, 8s svc cache / 15s proc cache |
| Service enabled | `.tbcc-run` toggles + `.env` profile (`Test-TbccServiceUserEnabled`) | file reads |
| API health / conflicts / focus | HTTP `127.0.0.1:8000/health/system` | 2s timeout, 15s fail-backoff |
| Ops alerts | HTTP `127.0.0.1:8000/ops/alerts/poll` | 2s timeout |
| Error hub tail | `.tbcc-run/error-hub.log` (`Read-TbccErrorHubTail`, last 256KB) | file read |
| Process audit | `.tbcc-run/process-audit.json` (StackWatch, ~60s) | file read + JSON |

Snapshot output is **pure data** — hashtables / PSCustomObjects / `HashSet[int]` / primitives. No live CIM objects are parked in `$snap.Cache`/`.Service` (the `Win32_Process` list is consumed for regex inside acquisition and reduced to status strings). This is what makes moving acquisition to a background thread safe.

## C) Failure modes under meltdown

1. **Single-tick freeze (primary).** Under CPU/RAM pressure, WMI + netstat + HTTP in one tick block the pump for seconds → visible drag/paint stall. The re-entrancy guard does not help a single long tick.
2. **Double `netstat` spawn.** `Get-TbccListeningPortSet` runs twice per heavy tick (once inside the svc-cache refresh, once for infra LEDs) — two subprocess spawns competing for a starved scheduler.
3. **API hang tax.** TCP-accept-then-hang on `:8000` costs up to 4s (2s × 2 endpoints) of pump freeze on the first post-recovery call, before backoff engages.
4. **`Win32_Process` cache-miss stall.** The 15s proc cache is the biggest single blocker on a miss; a meltdown both slows the query and shortens effective cache value (more services flapping = more misses).
5. **Silent staleness (NEW — introduced by the Phase 1 async fix).** Today "the tick just finished" *is* the freshness guarantee — on-screen data is provably current. Moving acquisition off-thread flips this: if the producer stalls (wedged netstat) or dies (unhandled loop exception), the UI keeps painting **stale data with no visible freeze** — an invisible lie. The async design is not complete without staleness detection.
6. **Scrollbar chrome regression risk.** White WinForms scrollbar tracks are suppressed via `ShowScrollBar(SB_BOTH,false)` + wheel; they must be re-suppressed after every Services grid rebuild and on Handle/Resize/Layout. Any rebuild path that forgets this re-introduces white tracks.
7. **Handle-leak regressions.** Largely fixed via row/cell pooling (update-in-place, hide surplus) and rebuild-only-on-id-change; a naive `Clear()`/recreate in any new code re-opens the leak.
8. **Producer lifecycle leak (NEW).** A background acquisition thread that is not signalled to stop + disposed on `FormClosed` keeps hammering netstat/WMI after the window closes.

## D) Remote-deploy parity options

Goal: mirror the local `Invoke-Tbcc*` start/stop/status the panel calls today onto a remote host, while **the local Windows tray stays the source of truth** for Windows-hosted services.

- **Option 1 — Tailscale SSH to the home PC (recommended for parity spike).** Home PC joins the tailnet; operator's desktop runs `ssh <tailscale-host> powershell -File tbcc-stack-cli.ps1 -Action Status`. Reuses the existing CLI verbs (`tbcc/scripts/tbcc-stack-cli.ps1`) with zero new server surface. Read-only `Status` is safe to spike; `Start` must stay operator-gated to avoid a second bot instance → Telegram **409 conflict**.
- **Option 2 — Thin control agent over the existing FastAPI (`:8000`).** The stack already exposes `/ops/*` and `/health/*`. A small authenticated `/ops/service/{id}/{action}` endpoint would let a remote desktop drive the same `Invoke-TbccServiceMenuAction` semantics. Higher blast radius; out of scope until the local model is proven and auth is designed.
- **Option 3 — GHCR offload parity (existing pattern).** The scrape VM / GHCR patterns already show a container-image handoff to a remote host. For desktop parity this is heavier than needed but is the reference for "deploy an image remotely, keep control local."
- **Single-writer invariant (critical for all options).** Exactly one host may run a given bot session at a time. Any remote `Start` path must interlock with the local tray (a shared lease/lock, or hard operator confirmation) or it produces Telegram 409s and session-file lock storms. Local tray remains authoritative; remote is status-first, control-second.

## Concrete follow-ups (Phase 1+)

1. **[P1] Background snapshot producer.** Dot-source `tbcc-service-control.ps1` + `tbcc-supervisor-panel.ps1` into an MTA runspace; run the acquisition loop there; publish pure-data snapshots to a synchronized latest-slot. UI timer becomes a cheap applier (apply diffs + suppress scrollbars + reassert topmost only). Verified safe because both files are pure function/`$script:`-const definitions (no side-effecting top-level code) and the snapshot carries no live CIM objects.
2. **[P1] Silent-staleness detection.** Stamp/read `UpdatedAt`; when snapshot age exceeds ~2× the loop interval, dim/badge the status line (full) and footer (mini). Wrap each producer iteration in try/catch so one bad WMI/netstat call cannot kill the loop permanently.
3. **[P1] Producer teardown.** `FormClosed` signals the loop to stop and disposes the PowerShell/runspace instance — no orphan netstat thread after close.
4. **[P1] Graceful fallback.** If the producer fails to *start*, fall back to the existing synchronous in-tick snapshot so a runspace bug can never fully brick the panel.
5. **[P1] Dedup the double `netstat`.** Return `Ports` from `Update-TbccServiceStatusCache` and reuse it for infra LEDs instead of a second `Get-TbccListeningPortSet` call.
6. **[P2] Meltdown mode.** When the API is down / host is saturated, drop the expensive HTTP + WMI cadence and keep process/port LEDs alive within 5s (cheap netstat + cached process list only).
7. **[P2] Services density.** Pagination or virtualization for large service sets; global enable/disable if missing.
8. **[P3] Remote-deploy design + thin spike.** Design doc mapping remote start/stop to local `Invoke-Tbcc*`; safe read-only `Status` spike over Tailscale SSH; single-writer interlock to avoid 409s.

## Verification

- Parse: `powershell -NoProfile -Command "& { $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('tbcc\tools\tbcc-supervisor-panel.ps1',[ref]$null,[ref]$e); if($e){$e}else{'OK'} }"`
- Smoke (operator): relaunch tray supervisor; open Panel + Mini; confirm sparks update; drag twice after idle (no freeze); Services has no white scrollbar tracks; wheel scrolls; corner-resize works; Pin keeps caption colored on click-away; staleness badge appears if the stack is stopped mid-session.
- Stack status (operator): `powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\tbcc-stack-cli.ps1 -Action Status`
