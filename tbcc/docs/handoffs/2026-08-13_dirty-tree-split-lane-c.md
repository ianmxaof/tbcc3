# Lane C handoff — split remaining dirty tree (~297 paths)

**Date:** 2026-08-13  
**Branch:** `lane-c/aof-hub-p9-p10`  
**Already committed this session:** flavor resupply `024b594`, worker island hygiene (prior)

## Dirty tree snapshot

| Vertical | ~files | Top paths |
|----------|--------|-----------|
| **aof-hub** | 81 | `aof-forum/` — connect, live, ingest, admin bridge, Dockerfile |
| **tbcc backend** | ~120 | VIP/Stars howto, celery island, R2 export, companion credit, reddit |
| **tbcc extension** | ~6 | gallery, manifest 1.40.43, master-archive |
| **tbcc infra/ops** | ~15 | docker-compose revenue-island, deploy scripts, dashboard Docker |
| **misc** | rest | promo assets, `.github/workflows/tbcc-ui-ghcr.yml` |

## Recommended commit slices (mechanical — Lane C)

### Slice A — Island workers + celery (`~8 files`)
- `tbcc/backend/app/workers/celery_app.py`
- `tbcc/infra/docker-compose.revenue-island.yml`, `env.revenue-island.example`
- `tbcc/scripts/revenue-island/*.ps1`, `bootstrap-island.sh`
- `tbcc/backend/tests/test_celery_island_beat_gates.py`
- `tbcc/docs/REVENUE_ISLAND.md`, `SPRINT_STATE.md` patches

### Slice B — VIP / Stars / payment (`~25 files`)
- `telegram_stars_howto.py`, `aof_vip_checkout.py`, `fiat_checkout_labels.py`
- `payment_bot.py`, `payment_pipeline.py`, related tests

### Slice C — Hub→R2 + storage (`~15 files`)
- `storage_hub_r2_export*.py`, `export_storage_hub_to_r2.py`, media API bits
- `test_storage_hub_r2_export.py`, handoff `2026-08-12_storage-hub-r2-manifest.md`

### Slice D — AOF Forum P9/P10 remainder (`~81 files`)
- All `aof-forum/` untracked + modified — **separate repo path**; do not mix with tbcc backend commits

### Slice E — Extension 1.40.43 (`~6 files`)
- Bump manifest + gallery; run ext-errors protocol smoke after

## Out of scope for Lane C
- `.env`, `.tmp/`, `*.session*`, companion pose JPG binaries, `_staging/gemini/` assets

## Verification per slice
```powershell
cd tbcc/backend
py -3.13 -m pytest <TEST_MAP entry for slice> -x -q --tb=short
```

## Reverse report
`tbcc/docs/handoffs/2026-08-13_dirty-tree-split_report.md` — list commits created, files per slice, pytest results.

STOP after each slice for Cursor ACK.
