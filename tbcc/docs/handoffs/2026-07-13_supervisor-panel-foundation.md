# Claude Code handoff — TBCC Supervisor panel foundation

Paste the fenced block below into Claude Code. Cursor already shipped a first UX pass (Pin caption keep-active, hide scrollbars, +15% scale, pause refresh while drag/resize, Sizable form). Lane C owns the longer reliability + remote-deploy foundation.

---

```
# Goal
Make the TBCC Supervisor panel (WinForms PowerShell under tbcc/tools) an unbreakably reliable real-time ops relay, and design a path for desktop-based remote deployment/control of the same services the panel starts/stops today — without brittle UI-thread freezes, white scrollbar chrome, or focus/Pin UX surprises.

Definition of done (this handoff):
1. Written assessment: architecture gaps, failure modes under CPU/RAM meltdown, data freshness guarantees.
2. Concrete phased plan with files + verification commands.
3. Phase 1 implementation (or clearly scoped PR-ready diff): isolate snapshot work off the UI thread (or equivalent non-blocking queue), harden drag/move, dark/no scrollbar chrome that survives list rebuilds, pin/caption behavior documented + tested.
4. Short remote-deploy design note: how tray/supervisor commands map to a remote host (Tailscale/SSH/agent) while keeping local tray as source of truth for Windows.

# Scope
Repo root: c:\Powercore-repo-main\telegram_bot2

In scope:
- tbcc/tools/tbcc-supervisor-panel.ps1
- tbcc/tools/tbcc-supervisor.ps1 (how panel is launched / tray glue)
- tbcc/scripts/tbcc-service-control.ps1 (service start/stop semantics the panel calls)
- tbcc/docs/TBCC_PROTOCOLS.md (tray supervisor section — update only if behavior changes)
- Optional small helpers under tbcc/tools/ if extracting native types or snapshot worker

Out of scope:
- Live tray process starts from agent terminals (operator only)
- .env / secrets / Telegram sessions
- Rewriting dashboard React or backend FastAPI as the primary ops UI
- Cloud Agent / GCP scrape VM work unless citing existing patterns for remote deploy parity

# Constraints & gotchas
- WinForms STA: never stack health snapshots on drag (InteractionPaused / ENTERSIZEMOVE already started).
- Dual Mini + Full timers previously froze sparks — park/hide the other form; do not regress.
- Pin already uses SetWindowPos + TbccSupForm.KeepActiveCaption (WM_NCACTIVATE intercept). Preserve or improve; do not regress TopMost.
- Scrollbars: ShowScrollBar(SB_BOTH,false) + mouse wheel; white tracks must not return after svc grid rebuild.
- Default stack console is headless (TBCC_STACK_CONSOLE=headless) — do not reintroduce WT focus-steal defaults.
- PowerShell 5.1 compatible (no pwsh-only syntax) unless documented.
- Do not commit .env, .tbcc-run/, *.session*

# Verification
Parse check:
  powershell -NoProfile -Command "& { `$e=`$null; [void][System.Management.Automation.Language.Parser]::ParseFile('tbcc\tools\tbcc-supervisor-panel.ps1',[ref]`$null,[ref]`$e); if(`$e){`$e}else{'OK'} }"

Smoke (operator):
  1. Exit tray TBCC Supervisor fully, relaunch.
  2. Open Panel + Mini; confirm sparks update; Pin keeps caption colored when clicking away.
  3. Drag window twice after idle — no freeze, no "busy" spin, title stays responsive.
  4. Services/Hub: no white scrollbar tracks; wheel scrolls; resize from corner works; labels readable (~+15% baseline already).
  5. Toggle a non-critical service from panel if safe; confirm status matches stack-cli Status.

Stack status (operator, do not start bots from agent):
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\tbcc-stack-cli.ps1 -Action Status

# Working agreement
- Branch: feat/supervisor-panel-foundation (create if missing)
- Commit per completed phase with fix:/feat: why-first messages
- Do not push unless asked
- After Phase 1, pause for Cursor review before Phase 2–3 large rewrites

# Phases
## Phase 0 — Assess (write-only)
Read panel/supervisor/service-control. Document:
A) Refresh pipeline (what blocks UI thread)
B) Data sources (ports, process audit, /health, hub log)
C) Failure modes under meltdown
D) Remote deploy parity options (SSH to home PC / Tailscale / existing GHCR offload patterns)
Deliverable: tbcc/docs/handoffs/supervisor-panel-assessment.md
Verify: file exists; lists ≥5 concrete follow-ups

## Phase 1 — Reliability core (implement)
- Background or async-friendly snapshot queue; UI only applies diffs
- Keep InteractionPaused; ensure second drag after idle stays light
- Scrollbar suppression after every Services rebuild
- Persist size/position (optional small JSON under .tbcc-run — do not commit that JSON)
Verify: parse OK + smoke checklist above

## Phase 2 — Ops density
- Services pagination or virtualization; global enable/disable if missing
- Meltdown mode: drop expensive HTTP, keep process/port LEDs alive
Verify: with API down, panel still shows process/port state within 5s without paint glitch

## Phase 3 — Remote deploy design + thin spike
- Design doc: remote start/stop mirroring local Invoke-Tbcc* commands
- Thin spike only if safe: dry-run remote Status over Tailscale SSH (no bot Start unless operator confirms)
Verify: design doc; spike documented with commands; no live bot 409 conflicts

# Working preference
Prefer Desktop Auto / Claude Sonnet for mechanical extraction. Pull architecture choices that change tray ownership back to Cursor for review.
```
