# Reverse handoff — TBCC Supervisor panel foundation (Phase 0–1 + remote-deploy design)

- Branch: `feat/supervisor-panel-foundation`
- Head commit(s) this phase (hash + subject):
  - `2745b50` fix: eliminate cold-start UI freeze — don't sync-snapshot while producer is dot-sourcing
  - `87b6872` docs: remote-deploy design note — command mapping, single-writer lease, Tailscale spike
  - `86d2d2d` feat: Phase 1 supervisor-panel reliability — off-thread snapshot producer + staleness
  - `0a8223b` docs: Phase 0 supervisor-panel assessment — UI-thread block, freshness, remote parity
- Status: Phase 1 complete | needs Cursor review (paused before Phase 2–3 per working agreement)

## Done
- **Diagnosed the freeze root cause:** the panel acquired ALL data (netstat, `Win32_Process` WMI, `/health` HTTP, hub tail) synchronously inside the `WinForms.Timer` tick, which runs on the STA message pump — measured **6038 ms** for a cold tick with the API down (WMI cold + 2×2s HTTP timeouts). That was the drag/paint freeze duration.
- **Moved acquisition off the UI thread:** new background MTA runspace producer (`Start-TbccSupSnapshotProducer`) dot-sources `tbcc-service-control.ps1` + the panel and publishes pure-data snapshots to a `[hashtable]::Synchronized` latest-slot. The full + mini timer ticks are now cheap appliers (read slot, apply diffs, suppress scrollbars, reassert TopMost) — no netstat/WMI/HTTP on the pump in steady state.
- **Data-freshness guarantee:** because off-thread acquisition trades a visible freeze for *silent staleness*, the applier surfaces snapshot age — `STALE Ns` badge on the panel status line + mini footer past 8s (2× heavy interval), warm→crit by age/producing state. Freshness stamped at publish time (not loop-start) so a slow cold acquisition doesn't flash STALE right after it lands.
- **Unbreakable degradation:** each producer iteration is `try/catch`'d (one bad WMI/netstat call can't kill the loop); the tick self-heals a dead/wedged producer and falls back to a synchronous snapshot only if the runspace never comes up. `FormClosed` stops + disposes the runspace (no orphan netstat thread).
- **Cold-start freeze eliminated:** a producer still dot-sourcing (`Alive=false`, <2s) is now classified `initializing` (StartedAt stamp + 15s grace) and the tick skips to "starting monitor…" instead of running the 6s sync snapshot on tick 1 and discarding the producer coming up.
- **Efficiency cleanups:** deduped the double `netstat` per heavy tick (return `Ports` from `Update-TbccServiceStatusCache`, reuse for infra LEDs); Hub/Alerts ListBoxes rebuild only on a content-signature change (the ~1.2s applier cadence would otherwise churn them every tick).
- **Kept without regression:** `InteractionPaused` pause-on-drag, Pin/`KeepActiveCaption`, per-tick scrollbar suppression, mutual mini/full parking. (This branch also carries Cursor's previously-uncommitted first UX pass, bundled per operator decision — see Risks.)
- **Docs:** Phase 0 assessment (refresh pipeline, data sources, failure modes incl. silent-staleness, ≥5 follow-ups) and a remote-deploy design note (command mapping, single-writer lease invariant, Tailscale-SSH-first transport ranking).

## Files touched
- `tbcc/tools/tbcc-supervisor-panel.ps1` — background snapshot producer + start/stop/read helpers; full + mini ticks rewritten as cheap appliers with staleness + cold-start-safe fallback; Hub/Alerts diff-guards; netstat-dedup reuse.
- `tbcc/scripts/tbcc-service-control.ps1` — `Update-TbccServiceStatusCache` now returns `Ports` (one-line) so the panel stops spawning a second `netstat` per heavy tick.
- `tbcc/docs/handoffs/supervisor-panel-assessment.md` — Phase 0 written assessment (new).
- `tbcc/docs/handoffs/supervisor-remote-deploy-design.md` — DoD item 4 design note (new).

## Verification run
Parse check (both edited scripts) — **PASS**:
```
$ powershell -NoProfile -Command "& { $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('<file>',[ref]$null,[ref]$e); if($e){$e}else{'OK'} }"
tbcc/tools/tbcc-supervisor-panel.ps1 OK
tbcc/scripts/tbcc-service-control.ps1 OK
```

Isolated producer runspace smoke (read-only; started no services) — **PASS**. Producer dot-sources both scripts off-thread and publishes fresh snapshots; warm age <1.3s; STALE only during the cold warmup window:
```
t= 8s iters=0 producing=True stale=True  age=inf   | no-snap        (cold first heavy in progress)
t=10s iters=1 producing=True stale=False age=0.8   | cpu=50 ram=80.9
t=12s iters=2 producing=True stale=False age=1.3   | cpu=33 ram=81.3
```

Cold-start classification over the init window — **PASS** (producer NOT replaced during dot-sourcing; no sync snapshot on the pump):
```
t~  300ms State=initializing hasSnap=False sameSharedObj=True
t~ 3000ms State=initializing hasSnap=False sameSharedObj=True
t~ 9000ms State=initializing hasSnap=False sameSharedObj=True
t~11000ms State=ready        hasSnap=True  sameSharedObj=True
```

Single cold-vs-warm snapshot timing (evidence of the freeze that moved off-thread) — **PASS**:
```
Call 1: 6038 ms  cache=True ports=19 hub=56 err=[The operation has timed out.]   (cold, API down)
Call 2:  230 ms  cache=True ports=19 hub=56 err=[API down (retrying shortly)]     (warm, backoff)
```

Not run by Claude: WinForms/tray smoke (operator-only) and any stack Start (bots must not be started from the agent).

## Risks / open questions
- **WinForms integration is unproven by automated test.** The runspace producer + snapshot logic are validated in isolation, but the full panel's timer→applier path (paint cadence, scrollbar re-suppression after rebuilds, TopMost/Pin under click-away) can only be confirmed by the operator tray smoke below. Please confirm before merge.
- **Cursor's first UX pass was uncommitted and is bundled here.** HEAD's panel (1536 lines) had zero of Cursor's markers (`KeepActiveCaption`/`InteractionPaused`/`Hide-TbccControlScrollBars`); those UX changes were interleaved with Phase 1 in the same file and can't be cleanly git-split, so `86d2d2d` contains both. Confirm this bundling is acceptable, or advise how you want attribution handled.
- **Applier cadence changed 4000ms → 1200ms** (to keep sparklines smooth now that the tick is cheap). Confirm the faster UI cadence + diff-guarded ListBoxes don't flicker on your hardware.
- **Shared-singleton producer:** closing a *hidden* (parked) full panel while the mini is the active consumer stops the producer the mini uses; the mini self-heals next tick with one hitch (commented in code). Acceptable, or do you want per-form producers?
- **Staleness threshold = 8s, init grace = 15s.** Under a persistently-down API, the backoff-expiry heavy tick can run ~6s every ~15s and may briefly flash STALE. Confirm the thresholds feel right or tune.
- **Unrelated working-tree changes left untouched:** `tbcc/docs/CI_MERGE_GATES.md`, `tbcc/docs/SPRINT_STATE.md`, and untracked `2026-07-13_supervisor-panel-foundation.md` were not staged/committed by this phase.

## Operator smoke (Tray only)
1. Exit the tray TBCC Supervisor fully, then relaunch.
2. Open Panel + Mini; confirm CPU/RAM sparks update; Pin keeps the caption colored when you click away.
3. Drag the window twice after it's been idle — no freeze, no "busy" spin, title stays responsive.
4. Services/Hub: no white scrollbar tracks; mouse wheel scrolls; corner-resize works; labels readable.
5. Confirm first-open shows "starting monitor…" briefly, then fills (no multi-second frozen window).
6. Stop the stack mid-session (or block :8000) — confirm the `STALE Ns` badge appears on the status line / mini footer, then clears when data resumes.
7. Toggle a non-critical service from the panel if safe; confirm status matches `tbcc-stack-cli.ps1 -Action Status`.

## Do not
- Do **not** push the branch until Cursor ACK.
- Do **not** start bots / launch the stack from an agent terminal (409 + session-lock risk).
- Do **not** touch `.env` / secrets / `*.session*` / commit `.tbcc-run/`.
- Do **not** begin Phase 2 (meltdown mode / density) or Phase 3 (remote spike) until Cursor ACK.
