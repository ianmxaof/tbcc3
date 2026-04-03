# Telegram Bot Command Center (TBCC)

Unified system for scraping, storing media in Telegram Saved Messages, approval queue, and posting to channels.

## What's included (all phases)

- **Backend**: FastAPI, SQLAlchemy models (Media, Source, ContentPool, Bot, Subscription, Channel), DB session, API (bots, channels, media, pools, sources, subscriptions, jobs, import). CORS enabled for dashboard.
- **Services**: TelegramStorage (forward to Saved Messages + index by file_unique_id), album_service (chunk + post from Saved Messages), post_scheduler (interval-based posting).
- **Workers**: Celery scrape + poster + scheduler_worker + subscription cleanup; beat schedule every 5 min for scheduler, every 6 h for expiry.
- **Bots** (in `backend/bots/`): scraper_bot, admin_bot, subscription_bot. Run with `PYTHONPATH=backend` from repo root or from `backend/`.
- **Browser extension**: Toolbar icon opens the **gallery side panel** (click again to toggle closed in Chrome). **Capture** only runs on **http(s)** pages — if the focused tab is `chrome://` / `brave://` / etc., the extension picks another injectable tab in the same window when possible (otherwise refresh after focusing a normal site). Footer links **Gallery view (collected)**, **Quick tools**, **Extension options**, and **Dashboard** open inside the **same side panel** (iframes); click the **same link again** to return to the main capture/send UI so you can watch imports update while browsing. **Dashboard** embeds `http://127.0.0.1:5173` (run `npm run dev` in `tbcc/dashboard`). `vite.config.ts` sets `frame-ancestors` on the **dev** and **preview** servers so the app can load in the sidebar iframe; for a **production** static host, set the same header (or equivalent) on nginx/Caddy so framing is not blocked. Right-click image/video/link → "Send to TBCC"; calls `POST /import/url`. **Multi-site search**: select a username → **Multi-site search (username)** — dashboard or tabs; config in `extension/model-search-sites.json`. **Reverse image search**: right-click an **image** → **Reverse image search (fan-out)** — opens Google / TinEye / Yandex / Bing / SauceNAO (or your list in `extension/reverse-image-sites.json`) in one **dashboard** tab or multiple tabs; requires a **public http(s) image URL** (blob/data URLs are not supported). **Screenshot → reverse search**: popup **Capture tab → copy & open reverse search** (copies the visible tab to clipboard and opens upload/search tabs), or right-click the page → **Capture tab → screenshot for reverse search** (opens a helper tab with preview + Copy). Tab list: `extension/screenshot-upload-pages.json`. Options: **Extension options** (model search + reverse image). Side panel gallery (**Open gallery** in popup): **Download** (separate files) or **ZIP** (one `.zip` for digital bundle uploads).
- **Dashboard**: React + Vite + Tailwind + TanStack Query + Recharts. Panels: Media Library, Content Pools, Sources, Scheduler, Subscriptions, Bot Monitor. Proxy `/api` → backend.

## Quick start

1. Copy `tbcc/.env.example` to `tbcc/.env` and set `API_ID`, `API_HASH`, `ADMIN_TELEGRAM_ID`.
2. **Launch script (recommended):** `cd tbcc && .\start.ps1` — backend + dashboard; opens the dashboard at http://localhost:5173 in **Brave** if it is installed (otherwise your default browser). Use `-NoOpen` to skip opening a browser; use `-Open` to also open the API docs (Swagger). Use `.\start.ps1 -Full` to also start Redis (Docker) + Celery worker (required for "Post now").
3. **Restart API + payment bot (after `.env` changes):** `cd tbcc && .\restart-api-payment.ps1` — stops whatever is on port **8000**, stops `python -m bots.payment_bot` if running, then opens fresh **TBCC-Backend** and **TBCC-PaymentBot** windows. Use `.\restart-api-payment.ps1 -ApiOnly` to restart only the API.
4. **Promo images + ngrok (one script):** Install [ngrok](https://ngrok.com/download) and run `ngrok config add-authtoken …` once. Then `cd tbcc && .\setup-promo-tunnel.ps1` — starts **ngrok** (if needed), sets **`TBCC_PROMO_PUBLIC_BASE_URL`** from the tunnel URL, and runs **`restart-api-payment.ps1`**. Use `-SkipDocker` if Postgres/Redis are already up. Re-upload promos in the dashboard after it finishes.
5. **Manual start:**
   - Backend: `cd tbcc/backend && pip install -r requirements.txt && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude scripts --reload-delay 1`  
     With `--reload`, the **TBCC-Backend** window is your **API**. Brief `CancelledError` / `KeyboardInterrupt` traces when WatchFiles restarts the worker are normal—not HTTP failures. `--reload-delay 1` batches quick saves (e.g. two files) into one restart on Windows. Excluding `scripts` avoids reloads when editing `backend/scripts/`. To avoid reloader noise entirely while testing: same command **without** `--reload` (restart manually after edits).
   - Dashboard: `cd tbcc/dashboard && npm i && npm run dev` → http://localhost:5173
6. **Full stack (Postgres + Redis + Celery):** `cd tbcc/infra && docker compose up -d postgres redis` then run backend/dashboard as above. For scrapers, posting, and scheduling, also run Celery worker + beat (see infra/docker-compose.yml).
7. Optional: run admin bot (`python -m bots.admin_bot` from `backend/` with env set).
8. **Payment bot (subscriptions + digital packs):** Create a bot via [@BotFather](https://t.me/botfather), add `BOT_TOKEN=...` to `tbcc/.env`. Set `TBCC_API_URL` if the API is not on `http://localhost:8000`. Run: `cd tbcc/backend && python -m bots.payment_bot` (requires backend + Redis + Celery for channel access). **Checkout:** **Telegram Stars (XTR)** in-bot today; copy and roadmap also cover **crypto** & **card (fiat)** for the same catalog. **Pipeline:** catalog → Stars invoice → **pre-checkout** (validates payload, user, XTR amount vs API) → **successful_payment** → `POST /subscriptions` with `telegram_payment_charge_id` (**idempotent** replays). Commands: **/start**, **/help**, **/shop**, **/subscribe**, **/packs**, **/referral**, **/status** (command list is registered with Telegram so it appears in the **/** menu after the bot starts). **Referrals:** run `alembic upgrade head` so table `referral_codes` exists; `/referral` assigns a short **code** + `ref_<code>` link (`POST /referrals/ensure-code`). Legacy `ref_<telegram_user_id>` deep links still work. Dashboard: *subscription* vs *bundle* products; description + optional channel for access.

### External (wallet / manual) payments

- Run migrations so **`external_payment_orders`** exists (`alembic upgrade head`).
- In **/subscribe** and **/packs**, each product has **Stars** + **Wallet / manual**. The latter calls `POST /external-payment-orders/` and shows instructions with reference **`EPO-…`** (customize copy via **`TBCC_EXTERNAL_PAY_TEMPLATE`** — placeholders `{reference_code}` `{plan_name}` `{price_stars}`).
- Set **`TBCC_INTERNAL_API_KEY`** in `tbcc/.env` (same value for API + payment bot). If unset, the API allows creates (dev only — set a key in production).
- **Admin confirms** off-platform payment: `GET /external-payment-orders/pending` and `POST /external-payment-orders/{id}/mark-paid` with header **`X-TBCC-Internal-Key`** (see `/docs`). That fulfills the same subscription/bundle as Stars (`payment_method=manual`).

**Troubleshooting “stale” wallet errors:** `GET http://127.0.0.1:8000/health` should include **`external_payment_orders_impl`**. `GET http://127.0.0.1:8000/external-payment-orders/_impl` returns **`impl`** and **`module_file`**. If those don’t match your repo (or `/_impl` 404s), another process is bound to **:8000** — often Docker **`api`** from `docker compose` with an **old image** (`docker compose stop api` and use local Uvicorn, or `docker compose build api && docker compose up -d api`).

## Redis & Celery (required for posting)

- **Import via extension** works without Celery. **"Post now"** and scheduled posting require Redis + Celery.
- **Docker Desktop** must be running for Redis. Then: `cd tbcc && .\start.ps1 -Full`, or manually:
- Start Redis: `docker run -d -p 6379:6379 redis` or `cd tbcc/infra && docker compose up -d redis`.
- Run Celery worker: `cd tbcc/backend && python -m celery -A app.workers.celery_app worker -l info`.
- Run Celery Beat (scheduler): `cd tbcc/backend && python -m celery -A app.workers.celery_app beat -l info`.

### Go-live: referrals + daily AOF landing bulletin

- **Referrals** need the subscription bot + API + Redis + Celery (same stack as payments). Users get `/referral` and `ref_` links; rewards apply when **`REFERRAL_MODE=premium`** and the referee subscribes (see `REFERRAL_*` in `.env.example`).
- **Milestone “progress”** counts **paying subscribers in the bot**, not raw Telegram group member count — the copy in promos makes that explicit.
- **After each new subscription**, optional **`MILESTONE_PROGRESS_CHAT_ID`** — bot posts a short FOMO line to that chat (if set).
- **Daily landing bulletin** (Celery Beat task `aof-landing-bulletin`): configure in **Dashboard → Growth** (stored in DB, overrides env) or set **`TBCC_LANDING_BULLETIN_*`** in `.env`. Beat runs **hourly**; only your chosen **UTC hour** sends (no Celery restart when changing the hour). The bot must be able to post in that chat/topic.

### Scheduler & forum topics (subtopics)

- In **Dashboard → Scheduler**, after you pick a **channel** that is a **forum-enabled supergroup**, a **Forum topic** dropdown appears. Choose a topic to send that scheduled job into that subtopic (same `message_thread_id` as the extension’s “Forum topic” mode). **Main chat (no topic)** posts to the group’s general area, like a normal channel post.
- Topics are loaded from `GET /channels/{id}/forum-topics` (Telegram user session must be able to read the group). If the list is empty, the group may not have topics enabled or the account needs to join/have rights.
- **Pool interval posting** (Content Pools → automatic interval) still targets the channel/group **main chat** only — not a forum topic. Use **Scheduled Posts** for topic-targeted cron-style content.

## Troubleshooting

- **"Mojo is not defined" in browser console:** This is a Brave/Chromium internal error, not from the TBCC extension. Filter it in DevTools (Right‑click error → "Filter" / add `-Mojo` to hide) or ignore it.
- **Port 8000 in use:** Another process is using it. Use `netstat -ano | findstr :8000` to find the PID; stop it or use a different port.
- **Extension pools not syncing:** Ensure the backend is running at http://localhost:8000. The popup fetches pools on open; reopen the popup after creating pools in the dashboard.
- **Redis/Docker "cannot find file specified":** Docker Desktop is not running. Start Docker Desktop, then run `.\start.ps1 -Full` or `docker run -d -p 6379:6379 redis` manually.
- **"Post now" does nothing:** Redis + Celery worker must be running. The Telegram account (API_ID/API_HASH) is the "poster" — you are the poster. Ensure you are an admin of the target channel with post permissions.
- **Promo / invoice images missing in Telegram:** Telegram loads image URLs **from its own servers**, not your PC. Set **`TBCC_PROMO_PUBLIC_BASE_URL`** (preferred) or **`TBCC_PUBLIC_BASE_URL`** to your public **`https://`** API (e.g. ngrok), restart the backend, then **re-upload** promos — dashboard upload builds `{that host}/static/promo/...`. For **ImgBB**, use a **direct image** URL (`https://i.ibb.co/.../file.jpg`), **not** “Viewer links” (`https://ibb.co/...` — those are HTML pages). If Telegram rejects a photo, the bot retries the invoice **without** it so checkout still works. **Dashboard file upload** (`POST /subscription-plans/upload-promo-image`) **normalizes** images server-side (Pillow): EXIF orientation, max edge 4096px, output **JPEG** or **PNG** (if transparency fits under the size cap), so local uploads are stored in a Telegram-friendly form.
- **Channels / media / pools “vanished” after Postgres:** Schema migrations (`alembic upgrade head`) only create **tables**, not **data**. If you used SQLite before (`DATABASE_URL=sqlite:///./tbcc.db`), your rows lived in `tbcc.db` (usually under `tbcc/backend/` where you ran uvicorn). Pointing `DATABASE_URL` at PostgreSQL gives you a **new empty database** — that’s expected. **Recovery:** if `tbcc.db` still exists, run from `tbcc/backend`: `python scripts/sqlite_to_postgres.py --dry-run` then without `--dry-run` (Postgres must already be migrated). If you **recreated the Docker Postgres volume** or never had a SQLite file, restore from a backup only — nothing in the repo can recreate lost rows.

## Repo layout

- `backend/` — FastAPI app, models, API, services, workers, **bots/** (scraper, admin, subscription); **`scripts/sqlite_to_postgres.py`** — copy data from old SQLite `tbcc.db` into Postgres after switching `DATABASE_URL`
- `extension/` — Chrome/Brave TBCC Importer
- `dashboard/` — React + Vite dashboard
- `infra/` — docker-compose.yml
