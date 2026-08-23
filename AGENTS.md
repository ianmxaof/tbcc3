# AGENTS.md

This monorepo (cloned as `telegram_bot2`) contains two products:

- **`tbcc/`** — Telegram Bot Command Center: Python 3 FastAPI backend + Celery workers/bots + a React/Vite dashboard. This is the primary, fully runnable product.
- **`aof-forum/`** — a Next.js 14 media hub that depends on external cloud accounts (Supabase + Backblaze B2) and a Stash Docker container.

See `tbcc/README.md` and `aof-forum/README.md` for full product/feature docs. The many `.ps1` / `.cmd` helper scripts under `tbcc/` are Windows-only — on Linux use the manual commands below.

## Cursor Cloud specific instructions

Dependencies are installed by the startup update script: a Python venv at `/workspace/.venv` (TBCC backend + `pytest`/`pytest-asyncio`) and `node_modules` for `tbcc/dashboard` and `aof-forum`. Always use the venv's interpreter: `/workspace/.venv/bin/python`.

### TBCC backend (`tbcc/backend`) — primary service
- Runs with **zero external services**: `app/database/session.py` defaults `DATABASE_URL` to SQLite. Note `app/config.py` has a stale Postgres default that is NOT used for the DB engine. `app/main.py` loads env from `tbcc/.env` (gitignored). A minimal `tbcc/.env` setting `DATABASE_URL=sqlite:///./tbcc.db` is used for local dev.
- Start: `/workspace/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` (add `--reload` for hot reload). Health: `GET http://127.0.0.1:8000/health`.
- **Redis, Postgres, and Celery are optional** — only needed for "Post now"/scheduled posting/auto-tag. They are NOT running here (no Docker). The dashboard's red banner `redis_down` / `postgres_down` is EXPECTED in this minimal setup and does not block core use.
- Most collection routers use a **trailing slash** (e.g. `POST /pools/`, `POST /channels/`); a pool requires an existing `channel_id`.
- Tests use in-memory SQLite. CI (`.github/workflows/tbcc-backend-tests.yml`) only gates on these 4 files: `tests/test_content_signals.py tests/test_growth_reaction.py tests/test_ops_workflow_runner.py tests/test_ops_tool_permissions.py`. The full suite (`python -m pytest -q tests/`) has ~11 pre-existing failures that are non-blocking in CI — do not treat them as environment breakage.

### TBCC dashboard (`tbcc/dashboard`)
- Dev: `npm run dev` → http://127.0.0.1:5173 (Vite, proxies `/api` → backend on :8000). Tests: `npm run test` (vitest).
- `npm run build` currently **fails on pre-existing TypeScript errors** (`tsc -b` step); use `npm run dev` for development.

### aof-forum (`aof-forum`)
- `npm run lint` and `npm run build` work offline. Running it end-to-end (`npm run dev`, ingest/stash workers) **requires cloud credentials** (Supabase URL + keys, Backblaze B2 keys) and a Stash Docker container — see `aof-forum/README.md`. Its `.env.example` uses Windows `C:/...` paths that must be changed on Linux.
