# Reverse handoff — cloud-only phase 2

**Branch:** `lane-c/phase2-cloud` (based on `origin/main` @ `fdbd65f`, PR #9 merge)
**Policy:** cloud-only — no TBCC processes started on the operator PC, no local tray/bots/DB.

## Setup

```
git fetch origin
git checkout -B lane-c/phase2-cloud origin/main
```
Local `lane-c/aof-hub-p9-p10` (tip `ae2b2fd`) is a strict ancestor of `origin/main` — confirmed
via `git merge-base origin/main lane-c/aof-hub-p9-p10` == `ae2b2fd` == that branch's tip, so
the checkout carried the working tree's uncommitted phase-2 files forward cleanly (git
three-way-merged each modified tracked file onto the new base; no conflicts, no `git stash`
needed). `git status --porcelain` after checkout: **140** paths (78 modified + 62 untracked),
close to the doc's "~130" estimate — variance likely from files resolved by the checkout-list/
companion-credit work already merged via PR #9.

## Phase 1 — Slice G: Reddit / Scrolller / market intel

**Status:** complete
**Commit:** `b8e01c3` — "feat(reddit): global cap, beacons, Scrolller probe + registry"
**Pushed:** yes, `origin/lane-c/phase2-cloud`

**Files touched (17):** `reddit_global_state.py`, `reddit_post_ledger.py` (new),
`reddit_post_service.py`, `reddit_rules.py`, `reddit_surface_caption.py` (modified),
`scrolller_reddit_registry.py`, `market_intel_scrolller_probe.py` (new),
`market_intel_worker.py` (modified), `reddit_beacon_plan.py` (new),
`aof_reddit_subreddit_registry.py` (modified), `reddit_go_live.py`,
`seed_reddit_beacons.py` (new), `reddit_post_dry_run.py` (modified), 3 new test files,
`REDDIT_STORIES_PROMO_PLAYBOOK.md` (new). Matched the source doc's Slice G file list
exactly — no additions or removals needed.

**Safety checks:** grepped diff + new-file contents for secret/password/API-key patterns —
clean.

**Verification:**
```
cd tbcc/backend && py -3.13 -m pytest tests/test_reddit_circuit.py tests/test_market_intel_scrolller_probe.py tests/test_scrolller_reddit_registry.py -x -q --tb=short
13 passed, 28 warnings in 0.67s
```
Warnings are pre-existing `datetime.utcnow()` deprecation notices in the reddit modules
themselves, not from this change.

**Island deploy:** not run this phase — batching per the source doc (deploy after G–I or
per-slice at operator discretion; proceeding to Phase 2 per instruction to keep moving).

**Risks / follow-ups:** none identified beyond the pre-existing deprecation warnings.

## Phase 2 — Slice H: Storage hub lane manual + admin bridge

**Status:** complete
**Commit:** `da1a2a7` — "feat(storage-hub): lane manual panels + forum admin bridge"
**Pushed:** yes, `origin/lane-c/phase2-cloud`

**Files touched (16):** matches the source doc's list, plus one addition —
`tbcc/backend/app/main.py`. Checked `main.py`'s full dirty diff before including it: its
*entire* diff was the `ops_admin_bridge` import + `app.include_router(ops_admin_bridge.router)`
line (2 insertions, 1 deletion total) — nothing else mixed in. Without it,
`ops_admin_bridge.py` would be committed but never wired into the FastAPI app, the same
dangling-reference pattern found in Phase 3 of the prior slice split (Slice C's worker,
Slice C's middleware carve-out). Included it.

**Confirmed resolved from the prior report:** `checkout_list_hub.py` (flagged in the
previous dirty-tree-split report as an untracked module already imported live by
`aof_growth_hub.sync_affiliate_network`) is now tracked and clean — landed via
`49d6e2d` before this branch's base. No longer a dangling reference.

**Safety checks:** grepped diffs and new-file contents for secret patterns — clean,
including `admin_bridge.py`/`ops_admin_bridge.py` specifically (auth-bridge code, checked
for hardcoded secret literals — none; secrets are read from env as expected).

**Verification:**
```
cd tbcc/backend && py -3.13 -m pytest tests/test_storage_hub_lane_manual.py tests/test_admin_bridge.py -x -q --tb=short
8 passed in 0.64s

python -c "import app.main"
IMPORT OK
```
The import check specifically confirms the new `ops_admin_bridge.router` wiring doesn't
break app startup.

**Island deploy:** not run this phase — continuing to batch per instruction.

**Risks / follow-ups:** none identified.

## Phase 3 — Slice I: Analytics direction + VIP status

**Status:** complete
**Commit:** `aa10b43` — "feat(analytics): direction ranking + VIP member status helpers"
**Pushed:** yes, `origin/lane-c/phase2-cloud`

**Files touched (8):** matches the source doc's list exactly.

**Cross-slice note:** `analytics.py`'s dirty diff (42 lines) carried two concerns in one
file: the new `/analytics/direction` route (this slice) *and* two Scrolller market-intel
routes (`/market-intel/probe/scrolller`, `/market-intel/scrolller/registry-suggestions`)
that expose `market_intel_scrolller_probe.py`/`scrolller_reddit_registry.py` — services
already committed in Phase 1 (Slice G) but whose HTTP routes were still uncommitted since
`analytics.py` wasn't in Slice G's file list. Committed both together rather than
hand-splitting the diff into hunks (git hunk-splitting across two features in active
development risks introducing a broken intermediate state for no real benefit — both
concerns land in the same push either way). `mcp-server/server.py`'s diff was cleanly
single-purpose (one new `analytics_direction` MCP tool calling the new route).

**Safety checks:** grepped diffs and new-file contents for secret patterns — clean.

**Verification:**
```
cd tbcc/backend && py -3.13 -m pytest tests/test_analytics_direction.py tests/test_vip_member_status.py -x -q --tb=short
8 passed, 2 warnings in 2.12s

py -3.13 -m pytest tests/test_aof_growth_hub.py -x -q --tb=short
4 passed in 0.66s

python -c "import app.main"
IMPORT OK
```
Warnings are pre-existing `datetime.utcnow()` deprecation notices, not from this change.

**Island deploy:** not run this phase — continuing to batch per instruction.

**Risks / follow-ups:** none identified.

## Phase 4 — Slice J: Dashboard Docker / GHCR UI

**Status:** complete
**Commit:** `a06e0d5` — "feat(dashboard): Docker + GHCR UI workflow, admin bridge wiring"
**Pushed:** yes, `origin/lane-c/phase2-cloud`

**Files touched (10):** matches the source doc's list, including
`tbcc/dashboard/public/bonusarrive-verify-a3048e.txt` — inspected: a domain-ownership
verification token (short hex string), not a secret — these files are *designed* to be
publicly servable, that's how the verification works, so committing it is correct not
risky.

**Cross-slice completion:** `App.tsx` and `DashboardHeaderToolbar.tsx` wire in
`AdminBridgeConsumer` and `OpenForumAdminButton` — components committed in Phase 2 (Slice
H) but not yet imported/rendered anywhere until this commit. `api.ts` adds the matching
`adminBridgeMint`/`adminBridgeConsume` client calls; verified their paths
(`/ops/admin-bridge/mint`, `/ops/admin-bridge/consume`) match the router prefix
(`/ops/admin-bridge`) registered in `ops_admin_bridge.py` (Phase 2). `api.ts` also fixes
two `/media` → `/media/` trailing-slash calls, unrelated to admin bridge but bundled in
the same file's diff — left in rather than hand-split.

**Build verification, with a documented deviation:** the doc's suggested `npm run build`
(`tsc -b && vite build`) **fails** — but on 34 pre-existing TypeScript errors across 9
files never touched by this branch (`EmojiFactoryRowDividers.tsx`,
`SchedulerIntervalCountdown.tsx`, `Analytics.tsx`, `BotAnalyticsPanel.tsx`,
`CompanionSettingsPanel.tsx`, `MediaLibrary.tsx`, `MiscPanel.tsx`,
`PoolCurateGallery.tsx`, `SecretarySettingsPanel.tsx`) — confirmed via
`npx tsc -b 2>&1 | grep` against every Slice J filename: zero matches. The
`Dockerfile` itself documents this as known debt ("Skip tsc -b in image builds
(pre-existing dashboard type debt); Vite emits production assets") and the real
build/deploy path is `npx vite build` alone. Ran that instead — the actual
production build path:
```
cd tbcc/dashboard && npx vite build
✓ 1003 modules transformed.
✓ built in 11.05s
```

**Safety checks:** grepped diffs and new-file contents for secret patterns — clean
(nginx template's `${TBCC_INTERNAL_API_KEY}` is an envsubst placeholder, not a literal;
GitHub workflow uses `${{ secrets.GITHUB_TOKEN }}`, GitHub's built-in token, not a custom
secret). Confirmed the GHCR workflow only triggers on push to `main`/`lean-stack-hardening`
or manual dispatch — pushing it to `lane-c/phase2-cloud` does not fire any CI run.

**Island deploy:** not run this phase — continuing to batch per instruction.

**Risks / follow-ups:** the 34 pre-existing `tsc -b` errors are unrelated to this branch
but exist in main already — not introduced or worsened here, just documented as
encountered. Not fixed (out of scope for a mechanical dirty-tree commit).
