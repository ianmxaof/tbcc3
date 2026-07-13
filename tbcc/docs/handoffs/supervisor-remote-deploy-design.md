# TBCC Supervisor — Remote Deploy/Control Design Note

_Design only (Phase 3 scoping). No live remote bot starts. Local Windows tray stays the source of truth. Companion to `supervisor-panel-assessment.md`._

## Goal

Let the operator drive the same start/stop/status the panel calls today (`Invoke-Tbcc*` / `tbcc-service-control.ps1`) against a **remote** host from their desktop, without ever running two copies of a bot session at once. The local tray remains authoritative for Windows-hosted services; remote is **status-first, control-second**.

## The one invariant that governs everything: single-writer

Exactly one host may run a given bot (Telegram session) at a time. Two concurrent starts → Telegram **409 Conflict** + `*.session` lock storms (see `[[tbcc-telegram-io-serialized]]`). Every remote path below must interlock with the local tray before any `Start`. Concretely:

- **Read paths (`Status`, `/health`, hub tail) are always safe** to run remotely and concurrently — spike these first.
- **Write paths (`Start`/`Stop`/`Restart`) require a lease.** Model: a single small lock file (e.g. `.tbcc-run/owner.lock` containing `{host, pid, acquiredAt}`) that any actor — local tray or remote agent — must hold to issue a start. The tray already owns process lifecycle; it is the natural default lease-holder. A remote `Start` must either (a) find the lease free, acquire it, then start; or (b) hard-fail with "local tray holds control." No silent takeover.

## Command mapping

The panel/tray control surface reduces to a handful of verbs already implemented in `tbcc-service-control.ps1` / `tbcc-stack-cli.ps1`:

| Local (today) | Remote equivalent | Safe to spike? |
|---|---|---|
| `tbcc-stack-cli.ps1 -Action Status` | `ssh <host> pwsh -File tbcc-stack-cli.ps1 -Action Status` | **Yes** (read-only) |
| `Update-TbccServiceStatusCache` / panel LEDs | remote `Status` → parse → render in local panel | Yes (read-only) |
| `Invoke-TbccServiceMenuAction -ServiceId x` (toggle) | remote `service-control -Action Start/Stop -Id x` **behind lease** | No — operator-gated |
| `Invoke-TbccStackLaunch` (start stack) | remote stack launch **behind lease** | No — operator-gated |

## Transport options (ranked)

1. **Tailscale SSH to the home PC (recommended).** Home PC joins the tailnet; desktop runs `ssh <tailscale-host> powershell -NoProfile -File …\tbcc-stack-cli.ps1 -Action Status`. Reuses existing CLI verbs, zero new server surface, MagicDNS + tailnet ACLs handle auth/identity. Best fit for a read-only parity spike.
2. **Thin authenticated endpoint on the existing FastAPI (`:8000`).** The stack already exposes `/ops/*` and `/health/*`. A new `POST /ops/service/{id}/{action}` (token-auth) would drive the same `Invoke-TbccServiceMenuAction` semantics over HTTP the panel already speaks. Higher blast radius; defer until the lease model + auth are designed and the SSH path is proven.
3. **GHCR image offload (existing pattern).** The scrape-VM / GHCR flow already demonstrates deploying an image to a remote host while keeping control local. Heavier than desktop parity needs, but it's the reference for "deploy remotely, keep the control plane local."

## Panel integration sketch (future, non-blocking)

- Add a `RemoteHost` field (nullable) to the panel UI state. When set, the **producer** (see Phase 1) additionally acquires a remote `Status` over SSH on the heavy cadence and merges it into the snapshot as a second service group ("remote"). This reuses the exact off-thread machinery Phase 1 built — remote SSH latency must never touch the UI thread, and the same staleness badge covers a wedged SSH call for free.
- Remote LEDs render read-only (grey border) until a lease is acquired; toggling a remote service prompts an explicit "acquire control from local tray?" confirmation.

## Thin spike (Phase 3, only on operator go)

```powershell
# Read-only, no bot starts, no 409 risk:
ssh <tailscale-host> "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Powercore-repo-main\telegram_bot2\tbcc\scripts\tbcc-stack-cli.ps1 -Action Status"
```

Success criteria: remote `Status` returns the same shape the local panel already parses; no live bot `Start` is issued; document the lease-acquisition flow before any remote write is attempted.

## Explicit non-goals

- No remote bot `Start` from an agent terminal — operator-only (matches Scope).
- No change to tray ownership of Windows process lifecycle.
- No secrets/session files leave the host; SSH/Tailscale identity only.
