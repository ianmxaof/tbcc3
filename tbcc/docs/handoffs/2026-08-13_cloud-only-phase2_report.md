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

## Note on process: continuous execution without per-phase ACK

Partway through Phase 1, the user instructed continuing through all phases without
pausing for Cursor ACK between them (overriding the source doc's "STOP — wait for ACK"
gates). Phases 1-7 below were executed back-to-back on that basis — verification and
safety checks still ran per commit, just without an ACK pause in between. Also observed
throughout: Cursor was committing directly to this same branch concurrently (`feaa2f2`,
`cc55e29`, `9c2b783` landed between my own commits, plus new in-flight work
`affiliate_sponsor_report.py` appeared late and was deliberately left untouched — not
mine to absorb). This is a shared branch, not exclusively mine.

## Phase 5 — Slice K: Misc backend churn (4 sub-batches)

The doc's own instruction ("split sub-batches... max ~15 files per commit") was followed
literally — 4 commits instead of one, grouped by `docs/TEST_MAP.md` area where a row
existed, otherwise by evident thematic cluster.

### K1 — Buffer X + affiliate + undress
**Commit:** `583ff06` — "feat(buffer-x): outbound gate spicy allowlist, affiliate seeding, undress tool"
**Files (11):** `buffer_x_link_order.py`, `buffer_x_outbound_guard.py`,
`prepend_luciddreams_x_armory.py` (new), `seed_promo_affiliate_links.py`,
`promo_bulk_import_ai_tools.json`, `undress_tool_client.py`,
`undress_video_poses.json` (new), `aof_copy_swipes/telegram_native_ads.json`, 3 tests.

**Pre-existing failure, confirmed via `git stash`:** `test_wrap_url_for_x_outbound_uses_manual_gate`
fails because `x_linkvertise_enabled()` defaults False (no `TBCC_X_USE_LINKVERTISE` env
var), so `wrap_url_for_x_outbound` returns bare-telegram URLs unchanged by design — the
test asserts it always wraps. Verified this fails identically on the clean
pre-Phase-5 baseline (`git stash` → run → `git stash pop`), so it's not something this
batch introduced. My dirty diff for that test file only *adds* a new unrelated test at
the end; it does not touch the failing assertion. Not fixed (same class of pre-existing
issue documented in earlier phases of this effort).

```
py -3.13 -m pytest tests/test_buffer_x_link_order.py tests/test_buffer_x_outbound_guard.py tests/test_undress_tool_client.py -q --tb=short
1 failed, 25 passed
```

### K2 — AOF/VIP + mainhub growth + lifecycle DM + loot
**Commit:** `43b0301` — "feat(aof): feed rhythm, mainhub growth/spotlight, lifecycle DM, loot economy"
**Files (13):** `aof_feed_rhythm_v2.py`, `aof_social_links.py`, `mainhub_channel_spotlight.py`,
`mainhub_growth.py`, `lifecycle_dm_copy.py`, `loot_lane_economy.py`,
`loot_preview_delivery.py`, `loot_bot.py`, 5 tests (incl. new `test_mainhub_growth.py`).
```
py -3.13 -m pytest tests/test_aof_feed_rhythm_v2.py tests/test_mainhub_channel_spotlight.py tests/test_mainhub_growth.py tests/test_lifecycle_dm_outreach.py tests/test_loot_lane_economy.py -q --tb=short
33 passed, 6 warnings
```

### K3a — Ops/QA/system health
**Commit:** `978dba5` — "feat(ops): system health checks, QA panel, celery queue ops, ship log"
**Files (9):** `album_service.py`, `celery_queue_ops.py`, `operator_sandbox.py`,
`ops_picture_report.py`, `qa_master_panel.py`, `qa_master_panel_handlers.py`,
`system_health.py`, `ship_log_context.json`, `test_celery_queue_purge.py`. Also ran three
existing (already-tracked, unrelated to this diff) test files covering the same modules
for extra confidence: `test_operator_sandbox.py`, `test_qa_master_panel.py`,
`test_system_health_island.py`.
```
py -3.13 -m pytest tests/test_celery_queue_purge.py tests/test_operator_sandbox.py tests/test_qa_master_panel.py tests/test_system_health_island.py -q --tb=short
16 passed in 126.66s  (slow — test_system_health_island.py exercises real timeout paths)
```

### K3b — Telegram content protection + scheduler/secretary/revenue
**Commit:** `88d3557` — "feat(telegram): content protection, scheduler/secretary/revenue updates"
**Files (16):** `archive.py`, `hub_panel_message.py`, `revenue_brief.py`,
`scheduled_post_service.py`, `sent_cache_composer.py`, `storage_deposit_panel_pins.py`,
`telegram_bot_markup.py`, `telegram_content_protection.py` (new), `traffic_pulse.py`,
`telegram_forum.py`, `poster_worker.py`, `secretary_bot.py`, 4 tests.

**Cross-batch dependency gap, disclosed rather than hidden:** `telegram_content_protection.py`
(new module, committed here) is imported at **module level** by `loot_preview_delivery.py`
(already committed in K2, `43b0301`) and function-locally by `album_service.py` (K3a,
`978dba5`). Both of those earlier commits therefore had a dangling import when
considered in isolation — resolved only once this commit landed. Root cause: the working
tree had the full ~130-file set present on disk throughout, so `python -c "import
app.main"` checks after K2/K3a passed regardless of what was actually committed vs. still
dirty — that check cannot distinguish "file exists in git" from "file exists on disk."
True per-commit isolation would require checking out each commit into a clean worktree,
which wasn't done. The **final** state (this commit onward) is consistent — confirmed via
`import app.main` succeeding after this commit — but anyone bisecting between K2/K3a and
K3b would hit an ImportError. Flagging this as a real limitation of the sub-batching
approach for a large pre-written diff, not a defect in the final result.
```
py -3.13 -m pytest tests/test_revenue_brief.py tests/test_scheduler_stall.py tests/test_telegram_content_protection.py tests/test_internal_api_auth.py -q --tb=short
30 passed, 23 warnings

python -c "import app.main"
IMPORT OK
```

**Safety checks (all of Phase 5):** grepped every diff and new-file content for secret
patterns — clean throughout.

**Island deploy:** not run — batching to Phase 7.

## Phase 6 — Slice F-b: Companion pose JPG tiles

**Status:** complete
**Commit:** `b00428a` — "assets(companion): refresh pose tile JPGs"
**Files:** 13 binary JPGs, ~2MB total (size checked before committing — well within a
reasonable single-commit range). The code that references these tiles
(`companion_poses.py`, its tests) was already on `main` via `d0e98d1` — this commit is
binary-only.

## Unnamed final batch: docs, CLAUDE.md/.claude settings, env example, misc

Not part of any phase in the source doc, but 31 legitimate files remained after Phase 6
that would otherwise leave the tree permanently dirty against this effort's own stated
goal ("commit the remaining ~130 uncommitted paths"). Bundled into one commit rather than
inventing new phase numbers for miscellany.

**Commit:** `75951f4` — "docs+chore: handoff docs, CLAUDE.md/.claude settings, env example, misc"

**Included:** 12 dated handoff/plan/report docs (2026-08-06 through 2026-08-13, including
this branch's own earlier reverse reports), `tbcc/CLAUDE.md` + `.claude/CLAUDE.md` +
`.claude/settings.json` + `tbcc/.claude/settings.json` (Claude Code shared project
settings — standard convention: `settings.json` is shared/committed,
`settings.local.json` is personal and gitignored), `.env.example` catch-up for features
already merged in earlier phases (VIP exclusive delay, weekly-mega public tease, mainhub
spotlight, network album size), `TBCC_PROTOCOLS.md`/`TEST_MAP.md`/
`loot-room-pinned-instructions.md` doc updates, `set-extension-island-api.ps1`, a one-off
`generate_knights_damned_edge_gemini.py` asset script, `ship_log_context.json` (had been
committed once already in K3a but was re-modified afterward — likely a live-refreshing
context snapshot; re-committed with its latest content), and the `powercore-verify`
static verification site (Cloudflare Pages deploy target for a domain-ownership token).

**Explicitly excluded, with reasons:**
- `docs/samples/knights_damned_edge/` — named out-of-scope in the source doc.
- `tbcc/static/powercore-verify/node_modules/` — installed dependency directory, never
  belongs in git.
- `.claude/settings.local.json`, `tbcc/.claude/settings.local.json` — personal
  machine-specific overrides; correctly excluded by this same commit's `.gitignore`
  addition (`**/.claude/settings.local.json`), verified by checking `git status` showed
  them absent after `git add .claude/ tbcc/.claude/`.

**Safety checks:** grepped every included file for secret patterns — clean.
`.claude/settings.json` reviewed in full (Claude Code permission allowlist — Bash command
patterns, no credentials).

## Post-Phase-5/6 regression pass

Re-ran every test file touched across Phases 5-6 together, from the final branch state
(after `75951f4`), to catch any cross-batch interaction the per-commit checks might have
missed:
```
py -3.13 -m pytest tests/test_reddit_circuit.py tests/test_market_intel_scrolller_probe.py tests/test_scrolller_reddit_registry.py tests/test_storage_hub_lane_manual.py tests/test_admin_bridge.py tests/test_analytics_direction.py tests/test_vip_member_status.py tests/test_aof_growth_hub.py tests/test_buffer_x_link_order.py tests/test_buffer_x_outbound_guard.py tests/test_undress_tool_client.py tests/test_aof_feed_rhythm_v2.py tests/test_mainhub_channel_spotlight.py tests/test_mainhub_growth.py tests/test_lifecycle_dm_outreach.py tests/test_loot_lane_economy.py tests/test_celery_queue_purge.py tests/test_operator_sandbox.py tests/test_qa_master_panel.py tests/test_revenue_brief.py tests/test_scheduler_stall.py tests/test_telegram_content_protection.py tests/test_internal_api_auth.py -q --tb=short
1 failed, 135 passed, 67 warnings in 138.06s

python -c "import app.main"
IMPORT OK
```
The 1 failure is the same pre-existing `test_wrap_url_for_x_outbound_uses_manual_gate`
documented under K1 — confirmed via `git stash`, not caused by this branch.

## Remaining dirty tree after all named work

```
git status --short | grep -v "companion_ui/poses|_staging/gemini|\.tmp/|assets/promo-generated"
 M tbcc/backend/bots/secretary_bot.py
?? tbcc/backend/app/services/affiliate_sponsor_report.py
?? tbcc/backend/tests/test_affiliate_sponsor_report.py
?? tbcc/docs/samples/knights_damned_edge/
?? tbcc/static/powercore-verify/node_modules/
```
The first three are Cursor's own in-flight work, committed/modified on this shared
branch *after* this session's Phase 5/6 commits landed — deliberately not touched
(not mine to absorb mid-development). The last two are explicitly out-of-scope
exclusions already covered above.
