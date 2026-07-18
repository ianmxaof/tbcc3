# AGENTS.md

Monorepo `telegram_bot2` with two products:

- **`tbcc/`** — Telegram Bot Command Center: FastAPI backend (`tbcc/backend`, port 8000), React+Vite dashboard (`tbcc/dashboard`, port 5173), Celery workers, Telegram bots, Chrome extension. Runs fully locally with SQLite; no cloud accounts required for basic dev.
- **`aof-forum/`** — Next.js 14 media hub (port 3001). Requires cloud accounts (Supabase Postgres+Auth, Backblaze B2) to run end to end.

Setup/launch scripts in the repo are Windows/PowerShell-first; on Linux use the plain commands below.

## Cursor Cloud specific instructions

### TBCC backend (`tbcc/backend`)
- Python deps install into a venv at `tbcc/backend/.venv` (gitignored). Activate with `source tbcc/backend/.venv/bin/activate`.
- **Use SQLite for local dev, not Postgres.** Set `DATABASE_URL=sqlite:///./tbcc.db` (also written to `tbcc/.env`). The app creates its schema via `Base.metadata.create_all` + SQLite column patches on startup (`app/main.py` `on_startup`), so you do **not** need Postgres or `alembic upgrade head`.
- **`alembic upgrade head` FAILS on SQLite** — migration `scheduled_text_posts` uses Postgres-only `ALTER COLUMN ... DROP NOT NULL`. Alembic migrations are Postgres-only; ignore alembic for SQLite dev and rely on startup `create_all`.
- Run: `cd tbcc/backend && source .venv/bin/activate && DATABASE_URL=sqlite:///./tbcc.db uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude scripts`
- Health checks: `GET /health` and `GET /health/db`. Most list routes need a trailing slash (`/pools/`, `/media/`, `/channels/`).
- Telegram/Celery/Redis features (posting, scheduling, bots) need `API_ID`/`API_HASH`, an authorized `.session` file, and Redis — not required for API + dashboard dev. Import-via-extension works without Celery; "Post now"/scheduled posts need Redis + Celery worker (queues `celery,post,scrape,subscription`) + Beat.
- Tests use in-memory SQLite fixtures (no Postgres/Redis). Required gate: `python -m pytest tests/test_content_signals.py tests/test_growth_reaction.py tests/test_ops_workflow_runner.py tests/test_ops_tool_permissions.py`. The full suite (`pytest tests/`) has ~12 known pre-existing failures and is non-blocking (see `.github/workflows/tbcc-backend-tests.yml`).

### TBCC dashboard (`tbcc/dashboard`)
- `npm install` then `npm run dev` (Vite on port 5173). Vite proxies `/api` → `http://localhost:8000`, so run the backend first. `npm run build`, `npm run test` (vitest) also available.

### AOF Hub (`aof-forum`)
- `npm install`; `npm run dev` (port 3001), `npm run lint`, `npm run build` all work **without** env vars (all routes are dynamically rendered; Supabase/B2 clients only read env at request time).
- Running the actual pages end to end (auth magic-link, feed, ingest) requires real cloud credentials in `aof-forum/.env.local` (see `.env.example`): Supabase (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) and Backblaze B2 (`B2_*`, `NEXT_PUBLIC_MEDIA_BASE_URL`). Schema is applied to Supabase via `npx supabase db push` (`supabase/migrations/*.sql`). `GET /api/health` works without creds and reports `supabase_env_configured`.
- Stash (Docker, port 9999) and the TBCC firehose (`TBCC_API_URL`) are optional content sources.
