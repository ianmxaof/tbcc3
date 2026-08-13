# Lane C handoff — cloud-only phase 2 (slices G–K + ops)

**Date:** 2026-08-13  
**Forward handoff for:** Claude Code (Lane C)  
**Reverse report:** `tbcc/docs/handoffs/2026-08-13_cloud-only-phase2_report.md`  
**Operator policy:** **No TBCC processes on the PC** — no tray backend, bots, Postgres, or Celery locally. Runtime = revenue island only.

## Context (what Cursor already shipped)

| Item | State |
|------|--------|
| PR #9 | **Merged** to `main` (`fdbd65f`) — island workers, forum P9/P10, flavor resupply, extension 1.40.43, checkout list, companion credits (`d0e98d1` on branch before merge) |
| Island deploy | Last tag `local-20260813-0620`; health OK |
| Checkout List | Bulletin posted (scheduler 166, 7 SFW links) |
| Flavor watch | Baseline in `tbcc/docs/FLAVOR_ROTATION_WATCH.md` — 356 sends / 2d, watch active |
| Ext-errors (cloud) | `https://api.powercore.app/health` **200**, `/tags/` **200** — extension QA = reload 1.40.43 against island API only |
| Local stack | **Stopped** — do not restart on operator PC |

## Dirty tree (~130 paths) — your job

Working tree on `lane-c/aof-hub-p9-p10` still has **uncommitted** phase-2 work. Plan doc: `tbcc/docs/handoffs/2026-08-13_dirty-tree-phase2-lane-c.md`.

**Slice F (companion credits code)** — already committed `d0e98d1`; **pose JPG binaries** still dirty (optional slice F-b).

### Remaining slices (commit order)

| Slice | Focus | TEST_MAP verify |
|-------|--------|-----------------|
| **G** | Reddit / Scrolller / market intel | `test_reddit_circuit`, `test_market_intel_scrolller_probe`, `test_scrolller_reddit_registry` |
| **H** | Storage hub lane manual + admin bridge | `test_storage_hub_lane_manual`, `test_admin_bridge` |
| **I** | Analytics direction + VIP status | `test_analytics_direction`, `test_vip_member_status` |
| **J** | Dashboard Docker / GHCR UI | `npm run build` in `tbcc/dashboard` |
| **K** | Misc backend churn (split by TEST_MAP) | per sub-batch |
| **F-b** | Companion pose JPGs only | none (binary) |

## Cloud-only rules (non-negotiable)

1. **Do not** run `tbcc-stack-cli.ps1 Start`, spawn bots, or start local Postgres/Redis/Celery on the operator PC.
2. **Do not** use `POST /bots/runtime/*/start` while diagnosing — island owns bots.
3. **Verify HTTP** against island: `https://api.powercore.app/health`, `/tags/`, `/companion/ops` (curl from any machine).
4. **pytest** — run in your Claude Code environment for gate proof; optional second gate = push + GitHub Actions `TBCC PR gate`.
5. **Deploy** after each slice (or batched after G–I): from repo root on a machine with SSH to island:
   ```powershell
   cd tbcc
   .\scripts\revenue-island\deploy-island-live.ps1 -SkipSeeds
   ```
   Island ships **working tree rsync**, not `git pull` on VPS. Deploy only after commits you intend to run live.
6. **Never commit:** `.env`, `*.session*`, `.tbcc-run/`, `.tmp/`, `_staging/gemini/`, `assets/promo-generated/`.

## Branch strategy

```bash
cd telegram_bot2   # monorepo root
git fetch origin
git checkout -B lane-c/phase2-cloud origin/main
# Port uncommitted files from lane-c/aof-hub-p9-p10 working tree OR cherry-pick if already committed locally
git status --porcelain   # expect ~130 paths once ported
```

Push branch after each slice; open PR to `main` when G–K complete (or one PR per slice if user prefers reviewability).

## Island smoke (after deploy)

```bash
curl -sS https://api.powercore.app/health
curl -sS https://api.powercore.app/tags/ | head -c 200
curl -sS https://api.powercore.app/companion/ops
```

Payment/loot smoke: operator Telegram only — do not duplicate bot processes.

## Extension QA (operator, cloud API)

Reload TBCC Importer **1.40.43**; gallery should hit island API first. If Errors panel shows `loadTagCatalog` warn while `/tags/` is 200 → **noise**. Uncaught exceptions in `gallery.js` → fix in extension slice.

## 48h flavor watch (passive)

Do not resync unless hook padding regresses. Evidence: MCP `analytics_post_events_summary` days=2 or island dry-run:

```bash
ssh root@5.161.53.91 'cd /opt/tbcc/infra && docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island exec -T api python scripts/resync_flavor_captions.py --dry-run'
```

---

## Paste-ready block for Claude Code

See fenced block in Cursor chat output (same content as `2026-08-13_cloud-only-phase2-lane-c` working agreement).
