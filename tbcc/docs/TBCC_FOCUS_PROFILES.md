# TBCC focus profiles (planned)

Goal: one coordinated **focus mode** across extension, dashboard, and tray supervisor — speed up batch import / Saved Messages uploads by reducing background contention, without breaking core paths.

## Problem today

| Piece | Exists? |
|-------|---------|
| Fast import queue + pause | Extension gallery |
| Redis `admin.session` lock | API + Celery |
| Stop legacy bots | Supervisor |
| Per-service restart / stop stack | Supervisor |
| `TBCC_AUTO_TAG_ON_IMPORT=0` | `.env` manual |
| Auto “import burst” profile | **No** |

Turning off **Beat** or sidecars manually helps, but nothing ties it to “user started a batch” or restores services after idle.

## Target profiles (v1)

### `import_burst`

**When:** User starts batch send/import (extension or dashboard).

**Keep running:** Postgres, Redis, TBCC-Backend, TBCC-Celery (`telegram` queue), optional TBCC-Dashboard.

**Stop or pause:**

- TBCC-Beat (scheduled posts, scrape tick, listening relay, loot promo)
- TBCC-NSFW-Detect, TBCC-CLIP-Categorize, TBCC-Lustpress (unless tagging during import)
- Optional bots: Payment, Secretary, Loot, MacroSearch, AlbumComposer
- Watch organizer process (if running)

**Flags (API / Redis, not only `.env`):**

- `import_focus_active=1` → API skips enqueueing new auto-tag tasks
- Extension pause unrelated queues (already has pause for *new* imports — different from focus)

**Restore:** After idle timeout (e.g. 15–30 min with no active import jobs) or explicit “End focus”.

### `watch_folder`

**When:** Watch organizer running or files in `TBCC_WATCH_INBOX`.

**Keep:** Backend, NSFW (:8001), CLIP (:8002) if niche folders on, watch organizer.

**Stop:** Beat, bots, heavy Celery scrape queue (optional).

### `minimal`

**When:** User choice or long idle.

**Keep:** Backend + Docker DBs only (or fully stopped stack).

## Architecture (recommended phases)

### Phase 1 — Ops API + state file (1–2 days)

- `GET /ops/focus` — current profile, active since, services map
- `POST /ops/focus` — `{ "profile": "import_burst" | "off", "idle_minutes": 30 }`
- Persist in Redis key `tbcc:focus:profile` + `tbcc:focus:until`
- Implement **stop/start** by calling existing `tbcc-service-control.ps1` functions from a small Python wrapper or PowerShell invoked from API (same as supervisor)
- **Do not** kill Backend/Celery/Redis during `import_burst`

**Detection (manual triggers first):**

- Extension: “Focus: Import” button → `POST /ops/focus`
- Supervisor: submenu under tray → same API
- Dashboard: Misc or System health panel → toggle

### Phase 2 — Automatic detect (2–3 days)

- **Import burst on:** first `POST /import/bytes` or gallery job start while profile is `off` → auto `import_burst` if `TBCC_FOCUS_AUTO_IMPORT=1`
- **Import burst off:** `GET /import/queue/status` shows 0 active + idle timer elapsed
- **Watch folder on:** watch organizer heartbeat file in `.tbcc-run/watch-organizer.pid` or API ping every 60s

### Phase 3 — Extension + dashboard UX (1–2 days)

- Extensity-style toggles: profile pill in gallery toolbar + dashboard banner
- Show what was stopped and one-click restore
- Link to `show-tbcc-processes.ps1` / supervisor status

### Phase 4 — Celery-aware throttling (optional)

- Beat stopped is enough for schedules; additionally:
  - Revoke or hold `scrape` / `media_auto_tag` tasks while `import_focus_active`
  - Lower `TBCC_THUMBNAIL_FETCH_CONCURRENCY` via runtime flag

## Safety rules

1. Never stop Postgres/Redis from focus profile (breaks everything).
2. Never stop Celery during `import_burst` (breaks uploads).
3. Stopping Beat is safe; manual “Trigger now” on scheduler still works via API.
4. Store **previous profile** to restore on `off`, not a blind “start full stack”.
5. Supervisor status cache stays async (tray opens fast); focus actions may take 1–2s.

## Related docs

- `docs/TBCC_PIPELINE.md` — import queue, pause
- `docs/TELEGRAM_OPS.md` — session lock, scraper naming
- `scripts/show-tbcc-processes.ps1` — process map

## Implemented (Phase 1 + partial Phase 2)

| Piece | Status |
|-------|--------|
| `GET/POST /ops/focus`, `/ops/focus/restore`, `/ops/focus/evaluate/auto` | Done |
| `scripts/tbcc-focus-profile.ps1` | Stops/starts optional services (never backend/celery) |
| Redis flags: `pause_auto_tag`, `import_focus`, `skip_sidecar_enrich` | Done |
| Auto `telegram_relief` when lock events ≥ threshold (`TBCC_FOCUS_AUTO_REACT=1`) | Done |
| Dashboard health banner: Focus buttons + session lock fix | Done |
| Tray supervisor: **Focus profile** submenu | Done |
| Background watch loop on API startup (25s) | Done |

### Profiles

- **import_burst** — stop Beat, sidecars, bots; keep Backend + Celery; `import_focus=1`
- **telegram_relief** — stop Beat + sidecars; pause auto-tag enqueue; auto on lock storm
- **watch_folder** — stop Beat/bots; keep NSFW/CLIP for organizer
- **off** — restore stopped services via PowerShell

### Auto import burst (Phase 2)

With `TBCC_FOCUS_AUTO_IMPORT=1` (default on):

1. **Immediate** — first `POST /import/bytes` fast-import enqueue → `import_burst`
2. **Queue spike** — watch loop (25s): active jobs ≥ `TBCC_FOCUS_IMPORT_JOBS_THRESHOLD` (default 2)
3. **Restore** — no active jobs for `TBCC_FOCUS_IMPORT_IDLE_RESTORE_MIN` minutes (default 15) → `off`
4. **Priority** — session lock storm still escalates to `telegram_relief` over import_burst

### Still planned

- Watch-folder heartbeat auto profile
