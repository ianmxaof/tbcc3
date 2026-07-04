# Erome Enhancer v4 — Browse Intel

Tampermonkey userscript + TBCC backend for Erome market signals → pool ranking.

## Files

| Path | Purpose |
|------|---------|
| `tbcc/tools/erome-enhancer/erome-enhancer.user.js` | Installable v4 script |
| `tbcc/tools/erome-enhancer/build_v4.py` | Rebuild from v3.3 base + patches |
| `tbcc/docs/erome-enhancer/SLEAZY_FORK_PUBLISH.md` | Sleazy Fork listing copy |
| `tbcc/docs/erome-enhancer/TAMPERMONKEY_SECURITY.md` | Brave/TM hardening checklist |

## Quick start

1. Tampermonkey → **disable** old `Erome Enhancer (alpha)`; install `erome-enhancer.user.js`.
2. Browse `/explore` with like counts on; open Enhancer → Export JSONL.
3. Drop file at `{tbcc_run}/erome-analytics/browse-intel-drop.jsonl` or Push to TBCC.
4. `POST /analytics/erome-browse-intel/sync-file` or wait for erome view sync celery task.
5. `GET /analytics/erome-browse-intel/summary` for top tags.

## API

- `POST /analytics/erome-browse-intel` — body `{ "rows": [ {...}, ... ] }`
- `POST /analytics/erome-browse-intel/sync-file` — ingest drop file
- `GET /analytics/erome-browse-intel/summary?days=30`

## Ranking

When `TBCC_EXPORT_FLYWHEEL_RANK_PICKS=1` and `TBCC_EROME_BROWSE_INTEL_RANK=1`, `rank_pool_media()` multiplies scores for approved media whose comma-tags overlap high-intel Erome tags. Used by scheduled pool posts and `post_pool_albums`.

## Rebuild userscript

```powershell
cd tbcc/tools/erome-enhancer
py -3.13 build_v4.py
```
