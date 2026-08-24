# Erome Enhancer

Tampermonkey userscripts for Erome grids. **Two builds:**

| Build | File | Audience |
|-------|------|----------|
| **Community** (Sleazy Fork) | `tbcc/tools/erome-enhancer/erome-enhancer-community.user.js` | Public — sorts/filters/scroll only |
| **Operator intel** | `tbcc/tools/erome-enhancer/erome-enhancer.user.js` | Private — + browse-intel JSONL / TBCC push |

## Files

| Path | Purpose |
|------|---------|
| `erome-enhancer-v3.3-base.user.js` | Feature body (build input) |
| `build_community.py` | Public header → `erome-enhancer-community.user.js` |
| `build_v4.py` | Intel patches → `erome-enhancer.user.js` |
| `tbcc/docs/erome-enhancer/SLEAZY_FORK_PUBLISH.md` | Sleazy Fork listing + AOF promo copy |
| `tbcc/docs/erome-enhancer/TAMPERMONKEY_SECURITY.md` | Brave/TM hardening (intel workflow) |

## Community (public)

```powershell
cd tbcc/tools/erome-enhancer
py -3.13 build_community.py
```

Install the generated community file in Tampermonkey, or paste Code + Info from `SLEAZY_FORK_PUBLISH.md` onto Sleazy Fork.

## Operator intel (private)

```powershell
cd tbcc/tools/erome-enhancer
py -3.13 build_v4.py
```

1. Tampermonkey → install `erome-enhancer.user.js` (keep community script disabled or renamed if both installed).
2. Browse `/explore` with like counts on; open Enhancer → Export JSONL.
3. Drop file at `{tbcc_run}/erome-analytics/browse-intel-drop.jsonl` or Push to TBCC.
4. `POST /analytics/erome-browse-intel/sync-file` or wait for erome view sync celery task.
5. `GET /analytics/erome-browse-intel/summary` for top tags.

## API (intel only)

- `POST /analytics/erome-browse-intel` — body `{ "rows": [ {...}, ... ] }`
- `POST /analytics/erome-browse-intel/sync-file` — ingest drop file
- `GET /analytics/erome-browse-intel/summary?days=30`

## Ranking

When `TBCC_EXPORT_FLYWHEEL_RANK_PICKS=1` and `TBCC_EROME_BROWSE_INTEL_RANK=1`, `rank_pool_media()` multiplies scores for approved media whose comma-tags overlap high-intel Erome tags. Used by scheduled pool posts and `post_pool_albums`.
