"""Deterministic playbooks injected into Cursor agent triage prompts."""

from __future__ import annotations

from typing import Any

PLAYBOOKS: dict[str, str] = {
    "session_sqlite_lock": """
## Playbook: session_sqlite_lock (SQLite database is locked)

**Symptom:** `sqlite3.OperationalError: database is locked` on Telethon `.session` files.

**Root cause:** Multiple processes share one session file (admin.session contention: API, Celery, bots, scrapers).

**Fix ladder (smallest → largest):**
1. **Immediate relief** — `POST /ops/focus` with profile `telegram_relief` or Secretary `/relief`.
2. **Dedicated sessions** — each long-lived bot/worker must use its own stem:
   - `admin_bot` → `admin_bot.session` (`TBCC_ADMIN_BOT_TELEGRAM_SESSION`, default `admin_bot`)
   - imports → `admin_import.session` (`TBCC_IMPORT_TELEGRAM_SESSION`)
   - poster → `admin_poster.session` (`TBCC_POSTER_TELEGRAM_SESSION`)
   - album composer → `admin_album.session`
   - Code: `app/utils/telethon_session.py` — `admin_bot_session_stem()`, `bootstrap_admin_bot_session_from_admin()`
3. **Bootstrap** — if `admin_bot.session` missing, copy from `admin.session` once (auto when `TBCC_ADMIN_BOT_AUTO_COPY_ADMIN_SESSION=1`).
4. **SQLite pragmas** — WAL + busy_timeout via `TBCC_TELEGRAM_SQLITE_BUSY_TIMEOUT_MS` (default 120000).
5. **Kill duplicates** — only one process per bot token; check supervisor tray for duplicate `admin_bot` / `secretary_bot`.
6. **Do not** run heavy scrapes while `telegram_relief` is active unless intentional.

**Code patch (PR only):** ensure new bots call `admin_bot_session_stem()` (or appropriate dedicated stem), never raw `admin.session`.
""".strip(),
    "session_lock_storm": """
## Playbook: session_lock_storm

Multiple lock events in the focus window (`TBCC_FOCUS_LOCK_EVENTS_THRESHOLD`, default 3 in 120s).

1. Auto-react may already apply `telegram_relief` when `TBCC_FOCUS_AUTO_REACT=1`.
2. Stop optional workers (scrape, relay) via focus profile — do not full-stack restart unless backend is dead.
3. Audit which services still share `admin.session` — split sessions per playbook above.
4. After calm (`TBCC_FOCUS_IDLE_RESTORE_MIN`), profile restores to `off`.
""".strip(),
    "uvicorn_orphans": """
## Playbook: uvicorn_orphans

Stale uvicorn/reload workers holding port 8000 or file handles.

1. `GET /ops/focus` — note active profile and stack state.
2. Prefer supervisor tray restart of **TBCC-Backend** only (not full Docker tear-down).
3. On Windows: verify single listener on `:8000` before restart.
4. If orphans persist after restart, inspect `.tbcc-run/error-hub.log` for the parent PID chain.
5. Code changes require PR — do not edit process management on main directly.
""".strip(),
    "worker_crash": """
## Playbook: worker_crash

Celery worker or bot process exited unexpectedly.

1. Identify queue from event meta (telegram, scrape, link, default).
2. Flywheel may propose `restart_stack_service` — **Approve in Secretary** before executing.
3. Check Redis connectivity (`REDIS_URL`) — worker crash often follows Redis blip.
4. Re-queue failed job only after worker is healthy (`GET /jobs` or dashboard).
""".strip(),
    "service_traceback": """
## Playbook: service_traceback

Unhandled Python traceback in API, worker, or bot.

1. Read traceback tail in triage bundle / `.tbcc-run/error-hub.log`.
2. Classify: import error (missing dep), DB migration, Telethon session, external API timeout.
3. Diagnose-only unless code is in `TBCC_CURSOR_TRIAGE_AUTO_FIX_ALLOWLIST` and PR-only mode applies.
4. Prefer minimal diff; add test when fix is non-obvious.
""".strip(),
    "api_port_duplicate": """
## Playbook: api_port_duplicate

Port 8000 already bound — duplicate backend or orphan uvicorn.

1. Restart TBCC-Backend via supervisor (flywheel deterministic lane).
2. If restart loops, run uvicorn_orphans playbook.
3. Never bind a second API on 8000 without changing `TBCC_API_PORT`.
""".strip(),
}


def playbook_for_code(code: str) -> str:
    return PLAYBOOKS.get(code.strip(), "")


def playbook_for_event(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    meta = event.get("meta") or {}
    code = str(meta.get("code") or meta.get("alert_id") or "").strip()
    return playbook_for_code(code)
