# Dirty tree split — reverse report (Lane C)

**Date:** 2026-08-13
**Branch:** `lane-c/aof-hub-p9-p10`
**Source doc:** `tbcc/docs/handoffs/2026-08-13_dirty-tree-split-lane-c.md`

Repo root is `telegram_bot2` (not a separate git repo per subdirectory — verified
`aof-forum/.git` does not exist, no `.gitmodules`). "Separate repo path" in the source doc
means "keep in its own commits," not an actual submodule boundary.

## Slice A — Island workers + celery — DONE

**Commit:** `606b9c7` — "feat(revenue-island): beat schedule gates + always-on UI compose profile"

**Files (17):**
- `tbcc/backend/app/workers/celery_app.py` (M) — beat schedule gated by
  `TBCC_REVENUE_ISLAND_ACTIVE`: scrape-scheduler-tick and market-intel probe/cycle default
  OFF on the island (no scrape queue worker there), storage-hub-r2-export beat task added,
  default ON on the island.
- `tbcc/docs/REVENUE_ISLAND.md` (M)
- `tbcc/infra/docker-compose.revenue-island.yml` (M) — always-on UI compose profile
- `tbcc/infra/env.revenue-island.example` (M) — new env vars matching the celery_app.py
  gates (`TBCC_REVENUE_ISLAND_ACTIVE`, `TBCC_SCRAPE_SCHEDULER_ENABLED`,
  `TBCC_STORAGE_HUB_R2_EXPORT_ENABLED`, etc.), UI-profile placeholders (Supabase/dashboard/
  forum URLs) — checked for real secrets, found none (all blank/placeholder or `${VAR:-}`
  compose substitutions)
- `tbcc/scripts/revenue-island/bootstrap-island.sh` (M)
- `tbcc/scripts/revenue-island/deploy-island-live.ps1` (M)
- `tbcc/scripts/revenue-island/setup-island-named-tunnel.ps1` (M)
- `tbcc/scripts/revenue-island/sync-admin-session.ps1` (M)
- `tbcc/scripts/revenue-island/sync-island-files.ps1` (M)
- `tbcc/backend/tests/test_celery_island_beat_gates.py` (new)
- `tbcc/scripts/revenue-island/enable-island-tailscale-serve.sh` (new)
- `tbcc/scripts/revenue-island/ensure-island-api-reachable.sh` (new)
- `tbcc/scripts/revenue-island/ensure-island-databases.sh` (new)
- `tbcc/scripts/revenue-island/install-island-database-watchdog.sh` (new)
- `tbcc/scripts/revenue-island/lock-island-ui-ports.sh` (new)
- `tbcc/scripts/revenue-island/sync-island-ui.ps1` (new)
- `tbcc/scripts/revenue-island/up-island-ui.sh` (new)

`tbcc/docs/SPRINT_STATE.md` was in the source doc's list but was not actually dirty —
skipped (nothing to commit).

**Safety checks before commit:** grepped the full slice diff for secret/token/password/
private-key patterns — no matches beyond placeholder examples and compose `${VAR:-}`
references. Reviewed `celery_app.py` and `env.revenue-island.example` diffs in full; both
coherent and cross-consistent (every new env var referenced in one appears used in the
other).

**Verification:**
```
cd tbcc/backend && py -3.13 -m pytest tests/test_celery_island_beat_gates.py -x -q --tb=short
4 passed in 2.55s
```
Covers the beat-schedule gating logic only. Nothing in this slice exercised the compose
profile, the 8 new/changed shell scripts, or `deploy-island-live.ps1` — no test coverage
exists for those, and they won't run until an actual island deploy. The island deploy process ships the working tree directly (not `git pull`), so
these scripts were very likely already live on the island before this commit — committing
them here is history hygiene (getting the repo to match what's already running), not a
change that will itself trigger anything on next deploy.

**Highest-risk line, flagged explicitly:** `celery_app.py`'s dotenv loader flipped
`load_dotenv(_p, override=True)` → `override=False` — process/compose env now wins over
the `.env` file (previously the reverse). Intentional per its comment (island compose
injects secrets/gates), but it means anyone running Celery locally with a stale
`DATABASE_URL`/`REDIS_URL`/bot token already exported in their shell will now silently
connect using that stale value instead of `.env`'s — no error, just an unexpected
connection target. Worth noting this repo already has the opposite convention elsewhere:
`app.utils.load_tbcc_dotenv()` (used by `seed_social_copy_templates.py` and
`resync_flavor_captions.py`, Phase 3) unconditionally overwrites `os.environ` from `.env`
regardless of what's already set — two dotenv loaders with opposite precedence now coexist
in the codebase. Not a reason to hold this commit (someone else's deliberate change,
correct for the island's actual failure mode), but a real source of local-vs-island
confusion if it comes up later.

**Note:** I did not author this code — it was already present in the working tree
(uncommitted) before this session. My work here was: review for safety, verify, group
into one coherent commit, document.

## Slice B — SKIP (pre-committed by Cursor)

**Commit:** `2c951d3` — "feat: VIP Stars howto + intro checkout surfaces" (19 files),
landed directly on `lane-c/aof-hub-p9-p10` by Cursor between Slice A's commit and its ACK.
Not touched by Lane C.

## Slice C — Hub→R2 + storage — DONE

**Commit:** `e0060d2` — "feat(storage-hub): R2 export worker + /media/export ingest bridge"

Re-checked the actual dirty-tree remainder rather than trusting the original doc's file
list (`cec6564` and part of `5e718d0` had already landed the export-skip/newest-first
service logic before Lane C started). Found the file list was smaller than "~15 files" —
the core service (`storage_hub_r2_export.py`) was already committed; what remained was:

**Files (6):**
- `tbcc/backend/app/workers/storage_hub_r2_export_worker.py` (new) — the Celery task
  `celery_app.py` already referenced in its beat schedule and `conf.include` since Slice A
  (`606b9c7`) — **that reference was dangling until this commit** (module didn't exist in
  git history, only on disk). Closed that gap.
- `tbcc/backend/scripts/export_storage_hub_to_r2.py` (new) — CLI wrapper, same service
- `tbcc/backend/app/api/media.py` (M) — new `/media/export` + `/media/export/r2/tick`
  endpoints for the aof-forum ingest bridge to poll
- `tbcc/backend/app/middleware/internal_api_auth.py` (M) — **security-relevant, not
  optional**: carves `/media/export` out of the public GET allowlist (`/media/` prefix is
  otherwise public for direct file/thumbnail serving). Without this the new endpoint would
  leak internal media metadata publicly. Wasn't in the original doc's file list; found by
  reading `test_media_export.py`'s first test (`test_media_export_not_public_get`) and
  tracing what it required.
- `tbcc/backend/tests/test_media_export.py` (new)
- `tbcc/docs/handoffs/2026-08-12_storage-hub-r2-manifest.md` (new)

**Deliberately left out of this slice:** `storage_hub_lane_manual.py` and its script/test/
doc cluster (`pin_storage_hub_lane_manuals.py`, `repost_storage_hub_panels.py`,
`cleanup_storage_hub_legacy_bot_messages.py`, `test_storage_hub_lane_manual.py`,
`STORAGE_HUB_PANEL_MANUAL.md`, plus modified `storage_hub_deposit_bot.py` /
`storage_hub_handlers.py`) — thematically "storage hub" but a functionally distinct
feature (pinned per-lane manual panels, not R2 export) not named in Cursor's Slice C scope.
Still dirty; a future slice.

**Safety checks:** grepped diff + new file contents for secrets — clean. Confirmed
`export_storage_hub_to_r2.py` uses `load_dotenv(p, override=True)` (file wins) — the
*opposite* of Slice A's `celery_app.py` change (process/compose wins) — another instance
of the dual dotenv-precedence pattern already flagged in Slice A's report, not something
introduced here.

**Verification:**
```
cd tbcc/backend && py -3.13 -m pytest tests/test_media_export.py -x -q --tb=short
4 passed in 1.44s
```

## Slice D — AOF Forum P9/P10 remainder — DONE

**Commit:** `da96df3` — "feat(aof-hub): forum P9/P10 remainder — connect/live/admin/upload, storage-hub ingest, admin bridge"

**Scope:** all of `aof-forum/` (88 files: 29 modified + 59 new, expanding the untracked
directories) in a **single commit**, not split. Considered splitting into
"storage-hub ingest" vs. "everything else" (Cursor's "own commit(s)" phrasing allows
either), but `lib/b2.ts` / `lib/media-url.ts` turned out to be genuinely cross-cutting —
used by the upload feature (`signedPutUrl` for P4 bulk upload), the storage-hub ingest
adapter, *and* the demo seed script — so any split would have misattributed those files to
one feature when they serve three. Kept as one commit rather than guess at a wrong
boundary without deep app-specific context. Matches the original doc's own framing of
Slice D as one bucket ("AOF Forum P9/P10 remainder").

**What's in it:** Connect directory (listing pages + sidebar/card components + 2 Supabase
migrations), live-embeds page, admin bridge (dashboard↔forum auth handshake), browser
upload (presigned B2 PUT, `UploadPanel.tsx`, upload API routes), dev password-auth
fallback for local Supabase rate-limit workaround, robots.ts/sitemap, and the Storage
Hub → forum ingest adapter (`workers/ingest/adapters/from-storage-hub.ts` + scripts +
`docs/STORAGE_HUB_INGEST.md`) — the forum-side counterpart to the R2 export path landed in
tbcc backend's Slice C (`e0060d2`).

**Excluded:** `aof-forum/.tmp/` (contained only a runtime log file,
`storage-hub-drain.log` — confirmed by listing contents before excluding, not just
pattern-matched). Confirmed `.env.local` (real secrets) was never in `git status` output
at all — already covered by `aof-forum/.gitignore`'s `.env*.local` pattern, so no explicit
exclusion needed for it.

**Safety checks:** grepped `git diff` output and every untracked file's content (not just
diffs — new files have no diff) for secret/password/API-key/token patterns with real-looking
values — clean. `.env.example` diff reviewed in full: only blank placeholders and
`you@example.com`-style examples added; one pre-existing truncated placeholder key
(`SUPABASE_SERVICE_ROLE_KEY=eyJhbGciU=r`, ~20 chars — too short to be a real JWT) was
already in the file before this diff (unchanged context line), not introduced here.

**Verification:**
```
cd aof-forum
npm run build   # ✓ Compiled successfully, 26/26 static pages generated, no errors
npm run lint    # ✔ No ESLint warnings or errors
```
No dedicated test script exists in `aof-forum/package.json` (only `build`/`lint`/`dev`).

## Slice E — Extension 1.40.43 — DONE

**Commit:** `3a16053` — "feat(extension): 1.40.43 — island-first API base, script load order fix, reachability retry"

**Files (6):** `gallery.html`, `gallery.js`, `manifest.json` (version 1.40.41 → 1.40.43),
`model-search-options.html`, `tbcc-api-client.js`, `tbcc-master-archive.js`.

**What's in it:** `TBCC_API_BASE_CANDIDATES` reordered in both `gallery.js` and
`tbcc-api-client.js` to try the revenue island (`api.powercore.app`, then its IP) before
`localhost`/`127.0.0.1` — consistent with the island now being the primary always-on
backend (Slice A). Fixed script load order in `gallery.html` and
`model-search-options.html`: `tbcc-api-client.js` now loads before
`tbcc-master-archive.js`, which apparently depends on it (the pre-existing order had it
loading after). Added one retry with a reachability re-check to `loadTagCatalog()` instead
of failing outright on the first transient connection error.

**Load-order claim, verified not assumed:** the commit message says
`tbcc-master-archive.js` "now depends on" `tbcc-api-client.js`. Checked this directly
rather than inferring it from the reorder alone: `git show 3a16053 -- tbcc-master-archive.js`
shows two new calls to `global.tbccFetchApiJson(...)`, which is defined in
`tbcc-api-client.js` (same function `gallery.js`'s diff also calls). The dependency is
real; the load-order fix was necessary, not cosmetic.

**Verification — stated honestly, not overclaimed:** no automated test suite covers these
specific files (`tbcc/extension/tests/*.test.mjs` covers abbrev-number/webp-convert/
zip-naming/infinite-scroll-stress — unrelated to this diff). The doc's suggested check
("run ext-errors protocol smoke after") is `/ext-errors`, a Cursor-side skill
(`~/.cursor/skills/tbcc-ext-errors/SKILL.md`) that expects a pasted screenshot from the
loaded extension's error console or live browser interaction — not something this session
can execute. What was actually done: full read of every diff, confirmed internal
consistency (the two files with `TBCC_API_BASE_CANDIDATES` were reordered identically;
the load-order fix in both HTML files moves the same script relative to the same
dependency), and a secret-pattern grep (clean; the one IP literal present,
`5.161.53.91`, was already in git history before this diff — not newly introduced).
**The operator should run `/ext-errors` after reloading the unpacked extension, since
that verification genuinely did not happen here.**

## Slices A–E: all done. Remaining dirty tree

```
git status --short | wc -l
167
```
**This is not a footnote — it's a second body of work roughly as large as the one this doc
scoped.** The source doc covered ~297 paths across five slices; those are done, but ~167
paths remain that were never named in any slice — companion bot (credit packs/checkout/
fulfill/poses/assets/menu/reveal-paywall/generation), reddit (post service/rules/surface-
caption/beacon-plan/global-state/ledger/scrolller-registry/circuit), admin bridge
(`admin_bridge.py`/`ops_admin_bridge.py`), `analytics_direction.py`,
`market_intel_scrolller_probe.py`, `telegram_content_protection.py`,
`vip_member_status.py`, plus companion pose JPGs and `_staging/gemini/` assets (both
explicitly out-of-scope per this doc).

**Highest-value item in it, flagged explicitly:** `tbcc/backend/app/services/checkout_list_hub.py`
is untracked (never committed, predates this session) but `aof_growth_hub.py`'s
`sync_affiliate_network()` already imports `sync_checkout_list_hub` from it — the same
class of dangling-reference gap Slice C closed for `storage_hub_r2_export_worker.py`
(uncommitted module, live import). It's live in shipped code today via the working tree,
same as everything else here, but it has no git history at all. Worth scoping as its own
slice before the rest of the 167, not buried alongside companion-bot/reddit work.

None of this was named in the source doc's Slice A–E breakdown. Not touched — a future
slice, scoped by Cursor/operator, not assumed here.

## STOP
All five slices resolved: A committed (`606b9c7`), B skipped (pre-landed as `2c951d3`),
C committed (`e0060d2`), D committed (`da96df3`), E committed (`3a16053`). Not pushed.
Awaiting Cursor `/cc-report` ACK.
