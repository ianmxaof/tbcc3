# Telegram session and SQLite lock storms

## What the errors mean

When you see **`sqlite3.OperationalError: database is locked`** in Celery logs during **`Telegram download failed for media id=7480`**, two different SQLite databases are usually contending:

| File | Used by |
|------|---------|
| `tbcc/backend/tbcc.db` | FastAPI (SQLAlchemy), Celery tasks that open a DB session |
| `tbcc/backend/admin.session` (or `admin_poster.session`) | Telethon’s internal SQLite session store |

On Windows, **one Celery worker** (`-P solo`, `worker_concurrency=1`) still processes tasks **one at a time**, but the **queue can be long**. Each thumbnail or auto-tag job that downloads from Telegram holds the Telethon session open and blocks the API when the dashboard loads many previews.

Secondary errors (`Task was destroyed`, `Event loop is closed`) are usually fallout from the lock/reconnect chaos, not the root cause.

## Immediate relief (dashboard should load again)

1. **Stop processes that share `admin.session`** (pick one primary writer):
   - Stop **scraper_bot** (tray supervisor or `tbcc-service-control.ps1 stop scraper`)
   - Avoid running **admin_bot** at the same time as the API if it uses the same session file

2. **Restart Celery worker** (clears stuck tasks; does not fix root cause):
   ```powershell
   # From tbcc folder, tray or:
   tbcc-service-control.ps1 stop celery
   tbcc-service-control.ps1 start celery
   ```

3. **Optional — pause auto-tag burst** while using the dashboard heavily:
   - In `tbcc/.env`: `TBCC_AUTO_TAG_ON_IMPORT=0` (stops new enrich/LLM jobs on import; existing queued jobs may still run)
   - Or temporarily stop Celery until you finish approving

4. **Use a separate poster session for posting** (does not fix thumbnails, but reduces poster vs admin contention):
   ```env
   TBCC_POSTER_TELEGRAM_SESSION=poster_bot
   TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1
   ```
   Run `python scripts/login_telethon_sessions.py` for `poster_bot` if needed.

5. **Verify API health** (browser or PowerShell):
   - `http://127.0.0.1:8000/health`
   - `http://127.0.0.1:8000/health/db`

## Code changes in this repo (thumbnail path)

- **`TBCC_THUMBNAIL_FETCH_CONCURRENCY`** (default `2`): limits parallel Telegram thumbnail downloads on the API process.
- **`TBCC_THUMBNAIL_FETCH_TIMEOUT_S`** (default `45`): avoids hanging forever on `/api/media/{id}/thumbnail`.
- Thumbnail endpoint returns **503** with a clear message when the session/DB is locked instead of blocking for 120s.
- **`configure_telethon_sqlite_session`** is applied when the admin Telethon client connects (WAL + busy timeout on session file).

## Longer-term recommendations

- **PostgreSQL** for production (`DATABASE_URL=postgresql://...`) — no SQLite file lock on the main app DB.
- **Never run two writers on the same Telethon session file** (one API + one bot + Celery all using `admin.session`).
- Consider a **dedicated Celery queue** for `media_auto_tag_worker` with rate limits so bulk approve does not enqueue hundreds of LLM+Telegram jobs at once.

## Celery queues (reference)

Default worker consumes: `celery,post,scrape,subscription` (see `start.ps1` / `TBCC-Celery.json`).

Auto-tag tasks: `app.workers.media_auto_tag_worker.auto_tag_media_llm` and `auto_tag_media_enrich` — triggered on import and bulk tag actions.
