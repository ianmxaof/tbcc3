# Cursor takeover — Supervisor panel (post–Lane C Phase 1)

**Date:** 2026-07-13  
**Branch:** `feat/supervisor-panel-foundation`  
**Owner now:** Cursor (Desktop Auto) — Lane C paused until next explicit `/handoff-cc`

## Already committed (Claude Code Phase 0–1)

| Commit | Subject |
|--------|---------|
| `0a8223b` | Phase 0 assessment |
| `86d2d2d` | Off-thread producer + staleness + UX bundle |
| `87b6872` | Remote-deploy design note |
| `2745b50` | Cold-start init grace (no sync snapshot during dot-source) |

Forward/report: `tbcc/docs/handoffs/2026-07-13_supervisor-panel-foundation.md` + `_report.md`  
CC report reviewed in Cursor earlier → **go smoke** (operator confirmed "everything works great").

## Uncommitted Cursor follow-ups (panel only — commit as one slice)

File: `tbcc/tools/tbcc-supervisor-panel.ps1` (~+270/−39 vs HEAD)

1. **Scroll / layout** — SERVICES row % grows; wheel scroll without killing AutoScroll; hide chrome only.
2. **Toggle Off** — MouseClick on LED/label subtree; `ForceRefresh` producer after toggle.
3. **Heat theme** — `Get-TbccHeatColor` green→amber→nuclear red (0%→100%); bars/sparks/Mini footer/Hub header.
4. **Hub tooltips** — hover CAUSE/FIX; Mini footer tip; Traceback demoted to warn (red reserved for meltdown).
5. **Ops:** `forum` forced `false` in `.tbcc-run/service-toggles.json` (not for git).

## Dirty tree warning

Working tree also has **unrelated** watermark / telegram.me / gate-link / extension churn.  
**Do not** stage those with the panel commit. Panel vertical only:

```
git add tbcc/tools/tbcc-supervisor-panel.ps1
git add tbcc/docs/handoffs/2026-07-13_supervisor-panel-foundation.md
git add tbcc/docs/handoffs/2026-07-13_supervisor-panel-foundation_report.md
# optional: TBCC_PROTOCOLS.md / claude-code-report registry docs if desired
```

## Phase 2 meltdown — shipped in code (verify via smoke)

Meltdown / `THROTTLE` / `STALE` already live in `tbcc-supervisor-panel.ps1` (+ `-Meltdown` on service-status cache). Prefatory notes that said “Phase 2 not started” are stale.

**Operator smoke (required):** Exit tray → relaunch → kill API mid-session → expect `THROTTLE`/`STALE`, Services LEDs still update, no UI freeze; toggle a non-bot optional service and match `tbcc-stack-cli.ps1 -Action Status`.

**Status truth ladder:** CLI Status / panel LEDs when API is down; `GET /ops/stack-status` only when API is up.

Polish only if smoke fails. Deep panel rewrite → Lane C only if smoke proves foundation bugs.

## Stop for operator

- Push: no until asked  
- Tray: Exit+relaunch after panel script changes  
- No agent bot Start
