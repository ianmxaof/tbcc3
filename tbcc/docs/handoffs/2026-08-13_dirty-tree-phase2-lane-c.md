# Lane C handoff — dirty tree phase 2 (~150 paths remain)

**Date:** 2026-08-13  
**Branch:** `lane-c/aof-hub-p9-p10`  
**Phase 1 report:** `tbcc/docs/handoffs/2026-08-13_dirty-tree-split_report.md`  
**Phase 1 slices A–E:** committed; checkout-list dangling ref closed in follow-up commit.

## Already landed (do not re-commit)

| Slice | Commit | Scope |
|-------|--------|-------|
| A Island/celery | `606b9c7` | Beat gates, UI compose, deploy scripts |
| B VIP/Stars | `2c951d3` | Stars howto, intro checkout |
| C Hub→R2 | `e0060d2` | R2 export worker, `/media/export` |
| D AOF Forum | `da96df3` | P9/P10 forum remainder |
| E Extension | `3a16053` | 1.40.43 island-first API |
| Flavor resupply | `024b594` | Hooks, PACKS 101, resync |
| Goblin/R2 fixes | `5e718d0`, `cec6564` | Teaser cadence, telegram_404 skip |
| Checkout List | *(post-split)* | `affiliate_content_lane`, `checkout_list_hub`, Secretary sfw intake |

## Remaining dirty tree (~150 paths)

Grouped by recommended **phase-2 commit slices**. Mechanical Lane C; stop after each slice for Cursor ACK.

### Slice F — Companion credits + poses (~25 files)

**Revenue:** companion Stars/credit checkout flywheel.

| Path | Notes |
|------|-------|
| `app/services/companion_credit_checkout.py` | new |
| `app/services/companion_credit_fulfill.py` | new |
| `app/services/companion_last_reveal.py` | new |
| `app/services/companion_poses.py` | new |
| `app/data/companion_credit_packs.py` | new |
| `app/services/companion_*.py` (M) | menu, generation, reveal_paywall, assets, body_prefs |
| `bots/companion_bot.py` (M) | |
| `scripts/seed_companion_credit_packs.py`, `import_companion_pose_tiles.py` | new |
| `tests/test_companion_credit_fulfill.py`, `test_companion_poses.py`, `test_companion_assets.py` (new) | |
| `tests/test_companion_menu.py`, `test_companion_reveal_paywall.py` (M) | |
| `data/companion_ui/poses/*.jpg` (M) | binary pose tiles — **exclude from PR if size blocks**; ship code first |

**Verify:** `pytest tests/test_companion_credit_fulfill.py tests/test_companion_poses.py tests/test_companion_menu.py -x -q`

### Slice G — Reddit / Scrolller / market intel (~20 files)

**Revenue:** long-term traffic; island has market-intel beat OFF.

| Path | Notes |
|------|-------|
| `app/services/reddit_global_state.py`, `reddit_post_ledger.py`, `reddit_post_service.py`, `reddit_rules.py`, `reddit_surface_caption.py` (M/new) | |
| `app/services/scrolller_reddit_registry.py`, `market_intel_scrolller_probe.py` | new |
| `app/workers/market_intel_worker.py` (M) | |
| `app/data/reddit_beacon_plan.py`, `aof_reddit_subreddit_registry.py` (M) | |
| `scripts/reddit_go_live.py`, `seed_reddit_beacons.py`, `reddit_post_dry_run.py` (M) | |
| `tests/test_reddit_circuit.py`, `test_scrolller_reddit_registry.py`, `test_market_intel_scrolller_probe.py` | new |
| `docs/REDDIT_STORIES_PROMO_PLAYBOOK.md` | new |

**Verify:** `pytest tests/test_reddit_circuit.py tests/test_market_intel_scrolller_probe.py tests/test_scrolller_reddit_registry.py -x -q`

### Slice H — Storage hub lane manual + admin bridge (~18 files)

**Ops / LT forum ingest path.**

| Path | Notes |
|------|-------|
| `app/services/storage_hub_lane_manual.py` | new |
| `app/services/admin_bridge.py`, `api/ops_admin_bridge.py` | new |
| `bots/storage_hub_*.py`, `storage_deposit_control_handlers.py` (M) | |
| `scripts/pin_storage_hub_lane_manuals.py`, `repost_storage_hub_panels.py`, `cleanup_storage_hub_legacy_bot_messages.py` | new |
| `dashboard/src/components/AdminBridgeConsumer.tsx`, `OpenForumAdminButton.tsx` | new |
| `docs/STORAGE_HUB_PANEL_MANUAL.md`, `ISLAND_UI_SURFACES.md` | new |
| `tests/test_storage_hub_lane_manual.py`, `test_admin_bridge.py` | new |

**Verify:** `pytest tests/test_storage_hub_lane_manual.py tests/test_admin_bridge.py -x -q`

### Slice I — Analytics direction + VIP status (~12 files)

| Path | Notes |
|------|-------|
| `app/services/analytics_direction.py`, `vip_member_status.py` | new |
| `app/api/analytics.py` (M) | |
| `scripts/analytics_direction_snapshot.py` | new |
| `tests/test_analytics_direction.py`, `test_vip_member_status.py`, `test_aof_growth_hub.py` | new |
| `mcp-server/server.py` (M) | if exposes analytics_direction tool |

**Verify:** `pytest tests/test_analytics_direction.py tests/test_vip_member_status.py -x -q`

### Slice J — Dashboard Docker / GHCR UI (~8 files)

| Path | Notes |
|------|-------|
| `dashboard/Dockerfile`, `dashboard/docker/`, `dashboard/.dockerignore` | new |
| `.github/workflows/tbcc-ui-ghcr.yml` | new |
| `scripts/deploy-powercore-verify.ps1` | new |
| `dashboard/src/App.tsx`, `api.ts`, header/toolbar/banner (M) | bundle with Docker slice |

**Verify:** dashboard `npm run build` + lint; no pytest.

### Slice K — Misc backend churn (batch or split further)

Modified services/bots not covered above (~40 files): `mainhub_growth`, `loot_preview_delivery`, `buffer_x_*`, `lifecycle_dm_copy`, `ops_picture_report`, `revenue_brief`, `telegram_content_protection`, `undress_tool_client`, secretary/loot/qa bots, etc.

**Strategy:** grep-driven sub-batches by feature (Buffer X order, loot lane economy, undress tool) using existing `TEST_MAP` rows — avoid one mega-commit.

### Out of scope (never commit)

- `tbcc/.env`, `*.session*`, `.tbcc-run/`
- `aof-forum/.tmp/`, `tbcc/.tmp/`, `tbcc/.claude/`
- `assets/promo-generated/`, `loot_tier_cards/_staging/gemini/` (generated art)
- `docs/samples/knights_damned_edge/` unless explicitly requested
- Companion pose JPGs if Git LFS / size policy applies

## Operator-only (not Lane C)

1. **Extension QA:** reload 1.40.43 → `/ext-errors` (backend must be up for `/tags/`)
2. **48h flavor watch:** `tbcc/docs/FLAVOR_ROTATION_WATCH.md`
3. **Checkout List live post:** `deploy_checkout_list_bulletin.py --execute --post` (needs Celery post + Telethon on island or tray)

## Verification template

```powershell
cd tbcc/backend
py -3.13 -m pytest <TEST_MAP paths for slice> -x -q --tb=short
```

## Reverse report target

`tbcc/docs/handoffs/2026-08-13_dirty-tree-phase2_report.md` — one section per slice F–K with commit SHAs and pytest output.

STOP after each slice for Cursor ACK.
