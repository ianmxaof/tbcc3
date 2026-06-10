# Telegram session and SQLite lock storms

## What the errors mean

When you see **`sqlite3.OperationalError: database is locked`** in Celery logs during **`Telegram download failed for media id=7480`**, two different SQLite databases are usually contending:

| File | Used by |
|------|---------|
| `tbcc/backend/tbcc.db` | FastAPI (SQLAlchemy), Celery tasks that open a DB session |
| `tbcc/backend/admin.session` | Dashboard thumbnails, light Telegram reads |
| `tbcc/backend/admin_import.session` | Bulk imports (channel scan, Saved Messages, Celery `telegram` queue) |
| `tbcc/backend/admin_poster.session` | Scheduled posts / pool auto-post |

On Windows, **one Celery worker** (`-P solo`, `worker_concurrency=1`) still processes tasks **one at a time**, but the **queue can be long**. Each thumbnail or auto-tag job that downloads from Telegram holds the Telethon session open and blocks the API when the dashboard loads many previews.

**Automated fix (2026+):** All `run_telegram_io` / `run_telegram_client_io` paths acquire a **Redis lock** (`tbcc:lock:admin_telegram_session`) so the API and Celery **wait in line** instead of failing. Set `TBCC_TELEGRAM_LOCK_TIMEOUT_S` (default 300) in `.env`. You should not need to stop Celery manually for Saved Messages batch sends.

Secondary errors (`Task was destroyed`, `Event loop is closed`) are usually fallout from the lock/reconnect chaos, not the root cause.

## Immediate relief (dashboard should load again)

1. **Stop processes that share `admin.session`** (pick one primary writer):
   - Tray supervisor → **Telegram session (admin.session)** → **Stop legacy scraper/admin bots (if any)**
   - This only kills **`python -m bots.scraper_bot`** or **`admin_bot`** if you started them manually — **not** part of `start.ps1 -Full`. Scheduled **ingest scrapes** run as Celery tasks (`run_scrape` on the `scrape` queue), not a permanent “scraper” window.
   - Avoid running **admin_bot** at the same time as the API if it uses the same session file

2. **Restart Celery worker** (clears stuck tasks; does not fix root cause):
   - Tray supervisor → **Telegram session (admin.session)** → **Restart Celery worker**
   - Or **Restart service** → **TBCC-Celery [down/up]**

3. **Optional — pause auto-tag burst** while using the dashboard heavily:
   - In `tbcc/.env`: `TBCC_AUTO_TAG_ON_IMPORT=0` (stops new enrich/LLM jobs on import; existing queued jobs may still run)
   - Or temporarily stop Celery until you finish approving

4. **Use separate Telethon session files** (same Telegram account is fine — copy `admin.session`):
   ```env
   TBCC_POSTER_TELEGRAM_SESSION=admin_poster
   TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1
   TBCC_IMPORT_TELEGRAM_SESSION=admin_import
   TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION=1
   ```
   Run `cd tbcc/backend && python scripts/login_telethon_sessions.py` (or `--copy-only` after admin login).
   Imports use `admin_import.session` + their own Redis lock so Celery channel scans do not block dashboard thumbnails on `admin.session`.

5. **Verify API health** (browser or PowerShell):
   - `http://127.0.0.1:8000/health`
   - `http://127.0.0.1:8000/health/db`

## Private groups (`-100…` id + `t.me/+` invite)

Scheduled posts and **pool auto-post** use **`admin_poster.session`** (see `TBCC_POSTER_TELEGRAM_SESSION`). Telethon cannot send to a bare numeric id until that account has the group in its entity cache (same as “Cannot find any entity corresponding to -100…” in Celery logs).

**Fix checklist:**

1. **Dashboard → Content pools → Channels** — set **Identifier** to the stable `-100…` id and **Invite link** to the current `https://t.me/+…` (rotate the invite in Telegram if the old link expired).
2. The poster account must be **in the group** (member or admin with post permission). Open each group once in Telegram logged in as that user.
3. After code updates or a DB reset, warm the poster cache:
   ```powershell
   cd tbcc\backend
   python scripts/warm_poster_peers.py
   ```
4. **Restart TBCC-Celery-Post** so the worker loads the new resolver (invite fallback + dialog scan).

Groups vs channels: Telegram supergroups use the same `-100…` id format; TBCC treats both the same for posting.

## Code changes in this repo (thumbnail path)

- **`TBCC_THUMBNAIL_FETCH_CONCURRENCY`** (default `2`): limits parallel Telegram thumbnail downloads on the API process.
- **`TBCC_THUMBNAIL_FETCH_TIMEOUT_S`** (default `45`): avoids hanging forever on `/api/media/{id}/thumbnail`.
- Thumbnail endpoint returns **503** with a clear message when the session/DB is locked instead of blocking for 120s.
- **`configure_telethon_sqlite_session`** is applied when the admin Telethon client connects (WAL + busy timeout on session file).

## Longer-term recommendations

- **PostgreSQL** for production (`DATABASE_URL=postgresql://...`) — no SQLite file lock on the main app DB.
- **Never run two writers on the same Telethon session file** — use `admin_import` for bulk imports and `admin_poster` for posting so `admin.session` stays free for dashboard reads.
- Consider a **dedicated Celery queue** for `media_auto_tag_worker` with rate limits so bulk approve does not enqueue hundreds of LLM+Telegram jobs at once.

## Celery queues (reference)

Default worker consumes: `celery,post,scrape,subscription` (see `start.ps1` / `TBCC-Celery.json`).

Auto-tag tasks: `app.workers.media_auto_tag_worker.auto_tag_media_llm` and `auto_tag_media_enrich` — triggered on import and bulk tag actions.
